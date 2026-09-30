const LANGUAGES = [
  ['auto', 'Auto-detect'],
  ['en', 'English'],
  ['as', 'অসমীয়া'],
  ['bn', 'বাংলা'],
  ['gu', 'ગુજરાતી'],
  ['hi', 'हिन्दी'],
  ['kn', 'ಕನ್ನಡ'],
  ['ml', 'മലയാളം'],
  ['mr', 'मराठी'],
  ['or', 'ଓଡ଼ିଆ'],
  ['pa', 'ਪੰਜਾਬੀ'],
  ['ta', 'தமிழ்'],
  ['te', 'తెలుగు'],
  ['ur', 'اردو'],
  ['ne', 'नेपाली'],
  ['kok', 'कोंकणी'],
  ['mai', 'मैथिली'],
  ['doi', 'डोगरी'],
  ['sa', 'संस्कृतम्'],
  ['sd', 'سنڌي'],
  ['ks', 'कॉशुर'],
]

export default function QuerySection({
  query,
  location,
  datetime,
  language,
  isAnalyzing,
  onQueryChange,
  onLocationChange,
  onDatetimeChange,
  onLanguageChange,
  onCoordinatesChange,
  onAnalyze,
}) {
  const useMyLocation = () => {
    if (!navigator.geolocation) {
      window.alert('GPS is not supported by this browser.')
      return
    }
    // Browsers only expose geolocation on a "secure context": https://, or
    // http://localhost. Opening the app on a phone via a plain
    // http://<LAN-IP>:5173 URL (common during same-network testing) means
    // this call fails immediately and silently unless we say why -- it's
    // not a bug in the app, it's the browser refusing an insecure origin.
    const isSecureContext =
      typeof window === 'undefined' || window.isSecureContext || window.location.hostname === 'localhost'
    if (!isSecureContext) {
      window.alert(
        'GPS requires a secure connection (HTTPS). It will not work over a plain ' +
        'http://<ip>:5173 link on mobile -- type the location manually, or serve the ' +
        'app over HTTPS / from localhost.',
      )
      return
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        onCoordinatesChange?.({ lat: coords.latitude, lon: coords.longitude })
        onLocationChange?.('Current location')
      },
      (error) => {
        const message =
          error.code === error.PERMISSION_DENIED
            ? 'Location permission was denied. Enable it in your browser settings, or type the location manually.'
            : 'Could not get your location. Type the location manually instead.'
        window.alert(message)
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
    )
  }

  return (
    <section className="orca-section query-section">
      <div className="section-heading">
        <h2>Ask ORCA</h2>
        <p>Ask in your language. ORCA detects it and coordinates specialist agents.</p>
      </div>

      <div className="query-form">
        <label className="field-label" htmlFor="orca-query">Your question</label>
        <textarea
          id="orca-query"
          className="query-input"
          rows={3}
          placeholder="e.g. Is it safe to fish tomorrow morning near my location?"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          disabled={isAnalyzing}
        />

        <div className="query-form__meta">
          <div className="field-group">
            <label className="field-label" htmlFor="orca-location">Location</label>
            <div className="location-row">
              <input
                id="orca-location"
                type="text"
                className="field-input"
                placeholder="Enter a city, coastal area or port"
                value={location}
                onChange={(e) => {
                  onLocationChange(e.target.value)
                  onCoordinatesChange?.(null)
                }}
                disabled={isAnalyzing}
              />
              <button type="button" className="secondary-btn" onClick={useMyLocation} disabled={isAnalyzing}>
                📍 Use GPS
              </button>
            </div>
          </div>

          <div className="field-group">
            <label className="field-label" htmlFor="orca-language">Response language</label>
            <select
              id="orca-language"
              className="field-input"
              value={language}
              onChange={(e) => onLanguageChange(e.target.value)}
              disabled={isAnalyzing}
            >
              {LANGUAGES.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
            </select>
          </div>

          <div className="field-group">
            <label className="field-label" htmlFor="orca-datetime">
              Date &amp; time <span className="optional">(optional)</span>
            </label>
            <input
              id="orca-datetime"
              type="datetime-local"
              className="field-input"
              value={datetime}
              onChange={(e) => onDatetimeChange(e.target.value)}
              disabled={isAnalyzing}
            />
          </div>
        </div>

        <button type="button" className="analyze-btn" onClick={onAnalyze} disabled={isAnalyzing || !query.trim()}>
          {isAnalyzing ? <><span className="spinner" aria-hidden="true" />Analyzing…</> : 'Analyze'}
        </button>
      </div>
    </section>
  )
}
