import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import CharactersPage from './pages/Characters'
import DatasetPage from './pages/Dataset'
import TrainingHistoryPage from './pages/TrainingHistory'
import StartTrainingPage from './pages/StartTraining'
import OngoingTrainingPage from './pages/OngoingTraining'
import TrainingDetailPage from './pages/TrainingDetail'
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
        {/* Training Routes - 3-level structure */}
        <Route path="/training" element={<TrainingHistoryPage />} />
        <Route path="/training/start" element={<StartTrainingPage />} />
        <Route path="/training/ongoing" element={<OngoingTrainingPage />} />
        <Route path="/training/:jobId" element={<TrainingDetailPage />} />
        <Route path="/generate" element={<ImageGenPage />} />
        <Route path="/video" element={<VideoPage />} />
        <Route path="/logs" element={<LogsPage />} />
      </Routes>
    </Layout>
  )
}

export default App
