import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import CharactersPage from './pages/Characters'
import TrainingPage from './pages/Training'
import ImageGenPage from './pages/ImageGen'
import VideoPage from './pages/Video'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/characters" replace />} />
        <Route path="/characters" element={<CharactersPage />} />
        <Route path="/training" element={<TrainingPage />} />
        <Route path="/generate" element={<ImageGenPage />} />
        <Route path="/video" element={<VideoPage />} />
      </Routes>
    </Layout>
  )
}

export default App
