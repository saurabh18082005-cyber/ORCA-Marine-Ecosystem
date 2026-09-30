import { useCallback, useState } from 'react'
import Header from './components/Header.jsx'
import QuerySection from './components/QuerySection.jsx'
import AgentCards from './components/AgentCards.jsx'
import RecommendationCard from './components/RecommendationCard.jsx'
import EvidenceCards from './components/EvidenceCards.jsx'
import MapSection from './components/MapSection.jsx'
import ExplanationSection from './components/ExplanationSection.jsx'

import { runRealAnalysis } from './services/orcaApiService.js'
import './App.css'

export default function App() {
  const [query, setQuery] = useState('')
  const [location, setLocation] = useState('')
  const [datetime, setDatetime] = useState('')
  const [language, setLanguage] = useState('auto')
  const [coordinates, setCoordinates] = useState(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [analysisData, setAnalysisData] = useState({ agents: {}, recommendation: null, evidence: [], explanation: { factors: [] }, map: null })
  const [hasAnalyzed, setHasAnalyzed] = useState(false)

  const handleAnalyze = useCallback(async () => {
    if (!query.trim() || isAnalyzing) return

    setIsAnalyzing(true)
    setAnalysisData({ agents: {}, recommendation: null, evidence: [], explanation: { factors: [] }, map: null })

    try {
      const result = await runRealAnalysis({ query, location, datetime, language, coordinates })
      setAnalysisData(result)
      setHasAnalyzed(true)
    } catch (err) {
      setAnalysisData({ agents: {}, recommendation: { riskLevel: 'MODERATE', title: 'Live analysis unavailable', reason: err.message, confidence: 0 }, evidence: [], explanation: { factors: [] }, map: null })
    } finally {
      setIsAnalyzing(false)
    }
  }, [query, location, datetime, language, coordinates, isAnalyzing])

  const showResults = hasAnalyzed || !isAnalyzing

  return (
    <div className="orca-app">
      <Header />

      <main className="orca-main">
        <QuerySection
          query={query}
          location={location}
          datetime={datetime}
          isAnalyzing={isAnalyzing}
          onQueryChange={setQuery}
          onLocationChange={setLocation}
          onDatetimeChange={setDatetime}
          language={language}
          onLanguageChange={setLanguage}
          onCoordinatesChange={setCoordinates}
          onAnalyze={handleAnalyze}
        />

        <AgentCards agents={analysisData.agents} />

        {hasAnalyzed && <section className="orca-section output-box"><div className="section-heading"><h2>ORCA Output</h2><p>Live response for your query</p></div><div className="output-box__content">{analysisData.recommendation?.reason || 'No live response returned.'}</div></section>}

        <RecommendationCard
          recommendation={isAnalyzing ? null : analysisData.recommendation}
          isAnalyzing={isAnalyzing}
        />

        {!isAnalyzing && showResults && (
          <>
            <EvidenceCards evidence={analysisData.evidence} isAnalyzing={false} />
            <MapSection mapData={analysisData.map} isAnalyzing={false} />
            <ExplanationSection explanation={analysisData.explanation} isAnalyzing={false} />
          </>
        )}

        {isAnalyzing && (
          <>
            <EvidenceCards evidence={[]} isAnalyzing />
            <MapSection mapData={analysisData.map} isAnalyzing />
          </>
        )}
      </main>

      <footer className="orca-footer"><p>ORCA · Live data only · No simulation fallback</p></footer>
    </div>
  )
}
