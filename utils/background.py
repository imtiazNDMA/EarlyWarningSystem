"""
Background task manager for running long-running operations asynchronously
"""

import threading
import logging
from typing import Callable, Any, Dict
import time

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """Simple background task manager using threading"""
    
    def __init__(self):
        self.tasks: Dict[str, threading.Thread] = {}
        self.task_results: Dict[str, Any] = {}
        self.task_errors: Dict[str, str] = {}
        
    def run_task(self, task_id: str, func: Callable, *args, **kwargs):
        """Run a function in a background thread
        
        Args:
            task_id: Unique identifier for the task
            func: Function to run in background
            *args, **kwargs: Arguments to pass to the function
        """
        def wrapper():
            try:
                logger.info(f"Starting background task: {task_id}")
                result = func(*args, **kwargs)
                self.task_results[task_id] = result
                logger.info(f"Completed background task: {task_id}")
            except Exception as e:
                logger.error(f"Error in background task {task_id}: {e}", exc_info=True)
                self.task_errors[task_id] = str(e)
            finally:
                # Clean up thread reference
                if task_id in self.tasks:
                    del self.tasks[task_id]
        
        thread = threading.Thread(target=wrapper, daemon=True)
        self.tasks[task_id] = thread
        thread.start()
        logger.debug(f"Started background thread for task: {task_id}")
        
    def is_running(self, task_id: str) -> bool:
        """Check if a task is still running"""
        return task_id in self.tasks and self.tasks[task_id].is_alive()
    
    def get_result(self, task_id: str) -> Any:
        """Get the result of a completed task"""
        return self.task_results.get(task_id)
    
    def get_error(self, task_id: str) -> str:
        """Get the error message if task failed"""
        return self.task_errors.get(task_id)
    
    def cleanup_old_results(self, max_age_seconds: int = 3600):
        """Clean up old task results (optional, for memory management)"""
        # For simplicity, we'll just clear all completed tasks
        # In production, you'd want to track timestamps
        completed_tasks = [tid for tid in self.task_results.keys()]
        for tid in completed_tasks:
            if not self.is_running(tid):
                if tid in self.task_results:
                    del self.task_results[tid]
                if tid in self.task_errors:
                    del self.task_errors[tid]


# Global instance
background_tasks = BackgroundTaskManager()
