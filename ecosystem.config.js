module.exports = {
  apps: [
    {
      name: 'early-warnings',
      script: '.venv/Scripts/waitress-serve.exe',
      args: '--listen=0.0.0.0:5001 wsgi:app',
      interpreter: 'none',
      env: {
        FLASK_ENV: 'production',
      },
    },
  ],
};
