import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import CharactersPage from './pages/Characters'
import DatasetPage from './pages/Dataset'
import TrainingPage from './pages/Training'
import ImageGenPage from './pages/ImageGen'
import VideoPage from './pages/Video'
import LogsPage from './pages/Logs'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/characters" replace />} />
        <Route path="/characters" element={<CharactersPage />} />
        <Route path="/dataset" element={<DatasetPage />} />
        <Route path="/training" element={<TrainingPage />} />
        <Route path="/generate" element={<ImageGenPage />} />
        <Route path="/video" element={<VideoPage />} />
        <Route path="/logs" element={<LogsPage />} />
      </Routes>
    </Layout>
  )
}

export default App
