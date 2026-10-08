export function AirQualityAttribution() {
  return (
    <p className="mt-2 text-[0.65rem] leading-relaxed text-ink/55">
      <a
        className="underline hover:text-ink"
        href="https://open-meteo.com/"
        target="_blank"
        rel="noreferrer"
      >
        Weather data by Open-Meteo.com
      </a>{' '}
      · CAMS data by{' '}
      <a
        className="underline hover:text-ink"
        href="https://atmosphere.copernicus.eu/"
        target="_blank"
        rel="noreferrer"
      >
        Copernicus
      </a>
    </p>
  )
}
