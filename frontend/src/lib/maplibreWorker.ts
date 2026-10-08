import { setWorkerUrl } from 'maplibre-gl'
// MapLibre 6 ships its worker as a separate file that it locates relative to its
// own module URL. Bundlers move that module, so hand it the worker's real URL.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'

setWorkerUrl(workerUrl)
