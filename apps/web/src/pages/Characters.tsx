import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Upload,
  Trash2,
  Zap,
  Image as ImageIcon,
  X,
  Eye,
  ChevronLeft,
  Grid,
  Loader2,
  Sparkles,
  Check,
  
  Wand2
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api, Character, GenerationJob } from '@/lib/api'
import { useNavigate } from 'react-router-dom'

interface PendingImage {
  file: File
  preview: string
}

interface StagedImage {
  url: string
  kept: boolean
  saving: boolean
}

export default function CharactersPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [isCreating, setIsCreating] = useState(false)
  const [selectedCharacter, setSelectedCharacter] = useState<Character | null>(null)
  const [newCharacter, setNewCharacter] = useState({
    name: '',
    description: '',
    trigger_word: '',
  })
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([])
  const [isUploading, setIsUploading] = useState(false)

  const { data: characters = [], isLoading } = useQuery({
    queryKey: ['characters'],
    queryFn: api.listCharacters,
  })

  const createMutation = useMutation({
    mutationFn: api.createCharacter,
    onSuccess: async (character) => {
      if (pendingImages.length > 0) {
        setIsUploading(true)
        try {
          const files = pendingImages.map(p => p.file)
          const dataTransfer = new DataTransfer()
          files.forEach(f => dataTransfer.items.add(f))
          await api.uploadImages(character.id, dataTransfer.files)
        } catch (error) {
          console.error('Failed to upload images:', error)
        }
        setIsUploading(false)
      }

      queryClient.invalidateQueries({ queryKey: ['characters'] })
      setIsCreating(false)
      setNewCharacter({ name: '', description: '', trigger_word: '' })
      pendingImages.forEach(p => URL.revokeObjectURL(p.preview))
      setPendingImages([])
    },
  })

  const deleteMutation = useMutation({
    mutationFn: api.deleteCharacter,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['characters'] })
      setSelectedCharacter(null)
    },
  })

  const handleCreate = () => {
    if (newCharacter.name && newCharacter.trigger_word) {
      createMutation.mutate(newCharacter)
    }
  }

  const handleCancelCreate = () => {
    setIsCreating(false)
    setNewCharacter({ name: '', description: '', trigger_word: '' })
    pendingImages.forEach(p => URL.revokeObjectURL(p.preview))
    setPendingImages([])
  }

  const handlePendingImageAdd = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newPending: PendingImage[] = Array.from(e.target.files).map(file => ({
        file,
        preview: URL.createObjectURL(file),
      }))
      setPendingImages(prev => [...prev, ...newPending])
    }
    e.target.value = ''
  }

  const handleRemovePendingImage = (index: number) => {
    setPendingImages(prev => {
      const updated = [...prev]
      URL.revokeObjectURL(updated[index].preview)
      updated.splice(index, 1)
      return updated
    })
  }

  const handleUploadToCharacter = async (e: React.ChangeEvent<HTMLInputElement>, characterId: string) => {
    if (e.target.files && e.target.files.length > 0) {
      try {
        await api.uploadImages(characterId, e.target.files)
        queryClient.invalidateQueries({ queryKey: ['characters'] })
        queryClient.invalidateQueries({ queryKey: ['character-images', characterId] })
      } catch (error) {
        console.error('Upload failed:', error)
      }
    }
    e.target.value = ''
  }

  // Render logic
  if (isCreating) {
    return (
      <div className="space-y-6 fade-in max-w-2xl">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={handleCancelCreate}>
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <h1 className="text-xl font-semibold text-foreground">New Character</h1>
        </div>

        <Card data-testid="character-form">
          <CardHeader>
            <CardTitle>Character Details</CardTitle>
            <CardDescription>
              Create a new character identity for LoRA training
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                data-testid="character-name-input"
                placeholder="e.g., John Smith"
                value={newCharacter.name}
                onChange={(e) => setNewCharacter({ ...newCharacter, name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="trigger">Trigger Word</Label>
              <Input
                id="trigger"
                data-testid="character-trigger-input"
                placeholder="e.g., johnsmith_person"
                value={newCharacter.trigger_word}
                onChange={(e) => setNewCharacter({ ...newCharacter, trigger_word: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                Unique word used in prompts to activate this character's likeness
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description (optional)</Label>
              <Textarea
                id="description"
                placeholder="Brief description of this character..."
                value={newCharacter.description}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setNewCharacter({ ...newCharacter, description: e.target.value })}
                rows={3}
              />
            </div>

            {/* Reference Images Section */}
            <div className="space-y-3 pt-4 border-t border-border">
              <div className="flex items-center justify-between">
                <Label className="text-base">Reference Images</Label>
                <label className="cursor-pointer">
                  <Button variant="outline" size="sm" asChild>
                    <span>
                      <Upload className="mr-2 h-4 w-4" />
                      Add Images
                    </span>
                  </Button>
                  <input
                    type="file"
                    multiple
                    accept="image/*"
                    className="hidden"
                    onChange={handlePendingImageAdd}
                  />
                </label>
              </div>

              {pendingImages.length === 0 ? (
                <div className="border-2 border-dashed border-border rounded-lg p-8 text-center">
                  <ImageIcon className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                  <p className="text-sm text-muted-foreground mb-2">
                    Drag & drop images here, or click to browse
                  </p>
                  <label className="cursor-pointer">
                    <Button variant="outline" size="sm" asChild>
                      <span>
                        <Upload className="mr-2 h-4 w-4" />
                        Select Files
                      </span>
                    </Button>
                    <input
                      type="file"
                      multiple
                      accept="image/*"
                      className="hidden"
                      onChange={handlePendingImageAdd}
                    />
                  </label>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">{pendingImages.length} image(s) selected</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        pendingImages.forEach(p => URL.revokeObjectURL(p.preview))
                        setPendingImages([])
                      }}
                    >
                      Clear All
                    </Button>
                  </div>
                  <div className="grid grid-cols-4 gap-2">
                    {pendingImages.map((img, index) => (
                      <div key={index} className="relative group aspect-square rounded-lg overflow-hidden bg-muted">
                        <img
                          src={img.preview}
                          alt={`Preview ${index + 1}`}
                          className="w-full h-full object-cover"
                        />
                        <button
                          onClick={() => handleRemovePendingImage(index)}
                          className="absolute top-1 right-1 p-1 rounded-full bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                    ))}
                    <label className="cursor-pointer aspect-square rounded-lg border-2 border-dashed border-border flex items-center justify-center hover:border-accent transition-colors">
                      <Plus className="h-6 w-6 text-muted-foreground" />
                      <input
                        type="file"
                        multiple
                        accept="image/*"
                        className="hidden"
                        onChange={handlePendingImageAdd}
                      />
                    </label>
                  </div>
                </div>
              )}

              <div className="bg-muted rounded-lg p-3 text-xs text-muted-foreground">
                <p className="font-medium text-foreground mb-1">Image Guidelines:</p>
                <ul className="list-disc list-inside space-y-0.5">
                  <li>Upload 10-20 high-quality photos</li>
                  <li>Include variety: angles, expressions, lighting</li>
                  <li>Avoid blurry or heavily filtered images</li>
                  <li>Subject should be clearly visible</li>
                </ul>
              </div>
            </div>
          </CardContent>
          <CardFooter className="flex justify-between border-t border-border pt-5">
            <Button variant="outline" onClick={handleCancelCreate} data-testid="cancel-btn">
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!newCharacter.name || !newCharacter.trigger_word || createMutation.isPending || isUploading}
              data-testid="create-character-btn"
            >
              {createMutation.isPending || isUploading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {isUploading ? 'Uploading...' : 'Creating...'}
                </>
              ) : (
                <>
                  <Plus className="mr-2 h-4 w-4" />
                  Create Character
                </>
              )}
            </Button>
          </CardFooter>
          {pendingImages.length > 0 && (
            <div className="px-6 pb-4 text-xs text-muted-foreground">
              <span>{pendingImages.length} image(s) will be uploaded</span>
            </div>
          )}
        </Card>
      </div>
    )
  }

  if (selectedCharacter) {
    return (
      <CharacterDetailView
        character={selectedCharacter}
        onBack={() => setSelectedCharacter(null)}
        onDelete={() => {
          if (confirm(`Delete "${selectedCharacter.name}"? This will also delete all training images.`)) {
            deleteMutation.mutate(selectedCharacter.id)
          }
        }}
        onUpload={(e) => handleUploadToCharacter(e, selectedCharacter.id)}
        onStartTraining={() => navigate('/training')}
      />
    )
  }

  return (
    <div className="space-y-6 fade-in">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">
            Create and manage character identities for LoRA training
          </p>
        </div>
        <Button onClick={() => setIsCreating(true)} data-testid="new-character-btn">
          <Plus className="mr-2 h-4 w-4" />
          New Character
        </Button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : characters.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <div className="rounded-full bg-muted p-4 mb-4">
              <ImageIcon className="h-8 w-8 text-muted-foreground" />
            </div>
            <h3 className="font-medium text-foreground mb-2">No characters yet</h3>
            <p className="text-sm text-muted-foreground max-w-sm mb-4">
              Create your first character to start training a personalized LoRA model
            </p>
            <Button onClick={() => setIsCreating(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Create Character
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3" data-testid="character-grid">
          {characters.map((character: Character) => (
            <CharacterCard
              key={character.id}
              character={character}
              onClick={() => setSelectedCharacter(character)}
              onUpload={(e) => handleUploadToCharacter(e, character.id)}
              onDelete={() => {
                if (confirm(`Delete "${character.name}"?`)) {
                  deleteMutation.mutate(character.id)
                }
              }}
              onTrain={() => navigate('/training')}
            />
          ))}
        </div>
      )}
    </div>
  )
}

interface CharacterCardProps {
  character: Character
  onClick: () => void
  onUpload: (e: React.ChangeEvent<HTMLInputElement>) => void
  onDelete: () => void
  onTrain: () => void
}

function CharacterCard({ character, onClick, onUpload, onDelete, onTrain }: CharacterCardProps) {
  return (
    <Card className="hover:border-border-hover transition-colors" data-testid="character-card" data-character-id={character.id}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-base">{character.name}</CardTitle>
            <CardDescription className="mt-1">
              <code className="text-xs text-accent">{character.trigger_word}</code>
            </CardDescription>
          </div>
          {character.lora_path && (
            <span className="status-badge status-success">Trained</span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {character.description && (
          <p className="text-sm text-muted-foreground mb-3 line-clamp-2">
            {character.description}
          </p>
        )}
        <button
          onClick={onClick}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors group"
        >
          <ImageIcon className="h-4 w-4" />
          <span>{character.image_count} images</span>
          <Eye className="h-3.5 w-3.5 ml-1 opacity-0 group-hover:opacity-100 transition-opacity" />
        </button>
      </CardContent>
      <CardFooter className="flex gap-2 border-t border-border pt-4">
        <Button variant="outline" size="sm" asChild className="flex-1">
          <label className="cursor-pointer">
            <Upload className="mr-2 h-3.5 w-3.5" />
            Upload
            <input
              type="file"
              multiple
              accept="image/*"
              className="hidden"
              onChange={onUpload}
            />
          </label>
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={character.image_count === 0}
          className="flex-1"
          onClick={onTrain}
        >
          <Zap className="mr-2 h-3.5 w-3.5" />
          Train
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="text-muted-foreground hover:text-destructive"
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          data-testid="delete-character-btn"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </CardFooter>
    </Card>
  )
}

interface CharacterDetailViewProps {
  character: Character
  onBack: () => void
  onDelete: () => void
  onUpload: (e: React.ChangeEvent<HTMLInputElement>) => void
  onStartTraining: () => void
}

function CharacterDetailView({ character, onBack, onDelete, onUpload, onStartTraining }: CharacterDetailViewProps) {
  const queryClient = useQueryClient()
  const [deletingImage, setDeletingImage] = useState<string | null>(null)
  const [showSynthetic, setShowSynthetic] = useState(false)

  const { data: imagesData, isLoading: imagesLoading } = useQuery({
    queryKey: ['character-images', character.id],
    queryFn: () => api.listImages(character.id),
  })

  const deleteImageMutation = useMutation({
    mutationFn: (filename: string) => api.deleteImage(character.id, filename),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['character-images', character.id] })
      queryClient.invalidateQueries({ queryKey: ['characters'] })
      setDeletingImage(null)
    },
  })

  const images = imagesData?.images || []

  return (
    <div className="space-y-6 fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={onBack}>
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-xl font-semibold text-foreground">{character.name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <code className="text-xs bg-muted px-1.5 py-0.5 rounded text-accent font-mono">
                {character.trigger_word}
              </code>
              {character.lora_path && (
                <span className="status-badge status-success">Trained</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" asChild>
            <label className="cursor-pointer">
              <Upload className="mr-2 h-4 w-4" />
              Upload Images
              <input
                type="file"
                multiple
                accept="image/*"
                className="hidden"
                onChange={onUpload}
              />
            </label>
          </Button>
          {character.lora_path && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowSynthetic(!showSynthetic)}
            >
              <Sparkles className="mr-2 h-4 w-4" />
              {showSynthetic ? 'Hide' : 'Generate'} Synthetic
            </Button>
          )}
          <Button
            size="sm"
            disabled={character.image_count === 0}
            onClick={onStartTraining}
          >
            <Zap className="mr-2 h-4 w-4" />
            Start Training
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="text-muted-foreground hover:text-destructive"
            onClick={onDelete}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Description */}
      {character.description && (
        <p className="text-muted-foreground">{character.description}</p>
      )}

      {/* Synthetic Image Generation */}
      {showSynthetic && character.lora_path && (
        <SyntheticGenerationPanel
          character={character}
          onImageSaved={() => {
            queryClient.invalidateQueries({ queryKey: ['character-images', character.id] })
            queryClient.invalidateQueries({ queryKey: ['characters'] })
          }}
        />
      )}

      {/* Image Grid */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Grid className="h-4 w-4 text-muted-foreground" />
              <CardTitle>Reference Images</CardTitle>
            </div>
            <span className="text-sm text-muted-foreground">{images.length} images</span>
          </div>
          <CardDescription>
            Upload 10-20 high-quality photos for best training results
          </CardDescription>
        </CardHeader>
        <CardContent>
          {imagesLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : images.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center border-2 border-dashed border-border rounded-lg">
              <ImageIcon className="h-10 w-10 text-muted-foreground mb-3" />
              <p className="text-sm text-muted-foreground mb-3">
                No images uploaded yet
              </p>
              <Button variant="outline" size="sm" asChild>
                <label className="cursor-pointer">
                  <Upload className="mr-2 h-4 w-4" />
                  Upload Images
                  <input
                    type="file"
                    multiple
                    accept="image/*"
                    className="hidden"
                    onChange={onUpload}
                  />
                </label>
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {images.map((filename: string) => (
                <div
                  key={filename}
                  className="relative group aspect-square rounded-lg overflow-hidden bg-muted"
                >
                  <img
                    src={`/api/characters/${character.id}/images/${filename}`}
                    alt={filename}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                  <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <Button
                      variant="destructive"
                      size="icon"
                      className="h-8 w-8"
                      disabled={deleteImageMutation.isPending && deletingImage === filename}
                      onClick={() => {
                        setDeletingImage(filename)
                        deleteImageMutation.mutate(filename)
                      }}
                    >
                      {deleteImageMutation.isPending && deletingImage === filename ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                  <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
                    <p className="text-xs text-white truncate">{filename}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Training Tips */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Training Guidelines</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3 text-sm">
          <div>
            <h4 className="font-medium text-foreground mb-1">Quantity</h4>
            <p className="text-muted-foreground">10-20 high-quality images work best. More is not always better.</p>
          </div>
          <div>
            <h4 className="font-medium text-foreground mb-1">Variety</h4>
            <p className="text-muted-foreground">Include different angles, expressions, and lighting conditions.</p>
          </div>
          <div>
            <h4 className="font-medium text-foreground mb-1">Quality</h4>
            <p className="text-muted-foreground">Use sharp, well-lit photos. Avoid blurry or heavily filtered images.</p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

interface SyntheticGenerationPanelProps {
  character: Character
  onImageSaved: () => void
}

function SyntheticGenerationPanel({ character, onImageSaved }: SyntheticGenerationPanelProps) {
  const [prompt, setPrompt] = useState(`A portrait photo of ${character.trigger_word}, professional lighting, high quality`)
  const [numImages, setNumImages] = useState(4)
  const [isGenerating, setIsGenerating] = useState(false)
  const [currentJob, setCurrentJob] = useState<GenerationJob | null>(null)
  const [stagedImages, setStagedImages] = useState<StagedImage[]>([])
  const [pollInterval, setPollInterval] = useState<number | null>(null)

  // Poll for job status
  useEffect(() => {
    if (!currentJob || !['pending', 'queued', 'running'].includes(currentJob.status)) {
      if (pollInterval) {
        clearInterval(pollInterval)
        setPollInterval(null)
      }
      return
    }

    const interval = window.setInterval(async () => {
      try {
        const updatedJob = await api.getGenerationJob(currentJob.id)
        setCurrentJob(updatedJob)

        if (updatedJob.status === 'completed' && updatedJob.output_paths.length > 0) {
          // Add generated images to staging area
          const newStaged: StagedImage[] = updatedJob.output_paths.map(path => ({
            url: `/api/generation/output/${path.split('/').pop()}`,
            kept: false,
            saving: false,
          }))
          setStagedImages(prev => [...prev, ...newStaged])
          setIsGenerating(false)
        } else if (updatedJob.status === 'failed') {
          setIsGenerating(false)
        }
      } catch (error) {
        console.error('Failed to poll job status:', error)
      }
    }, 2000)

    setPollInterval(interval)

    return () => {
      if (interval) clearInterval(interval)
    }
  }, [currentJob?.id, currentJob?.status])

  const handleGenerate = async () => {
    setIsGenerating(true)
    try {
      const job = await api.generateImages({
        prompt,
        negative_prompt: 'blurry, low quality, distorted, deformed',
        width: 1024,
        height: 1024,
        steps: 20,
        guidance_scale: 3.5,
        seed: null,
        lora_id: character.id,
        lora_strength: 1.0,
      }, numImages)
      setCurrentJob(job)
    } catch (error) {
      console.error('Failed to start generation:', error)
      setIsGenerating(false)
    }
  }

  const handleKeepImage = async (index: number) => {
    const image = stagedImages[index]
    if (image.kept || image.saving) return

    setStagedImages(prev => prev.map((img, i) =>
      i === index ? { ...img, saving: true } : img
    ))

    try {
      // Fetch the image and upload it to the character
      const response = await fetch(image.url)
      const blob = await response.blob()
      const file = new File([blob], `synthetic_${Date.now()}.png`, { type: 'image/png' })

      const dataTransfer = new DataTransfer()
      dataTransfer.items.add(file)

      await api.uploadImages(character.id, dataTransfer.files)

      setStagedImages(prev => prev.map((img, i) =>
        i === index ? { ...img, kept: true, saving: false } : img
      ))

      onImageSaved()
    } catch (error) {
      console.error('Failed to save image:', error)
      setStagedImages(prev => prev.map((img, i) =>
        i === index ? { ...img, saving: false } : img
      ))
    }
  }

  const handleDiscardImage = (index: number) => {
    setStagedImages(prev => prev.filter((_, i) => i !== index))
  }

  const handleClearAll = () => {
    setStagedImages([])
  }

  const handleKeepAll = async () => {
    for (let i = 0; i < stagedImages.length; i++) {
      if (!stagedImages[i].kept) {
        await handleKeepImage(i)
      }
    }
  }

  return (
    <Card className="border-accent/50">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-accent" />
          <CardTitle>Generate Synthetic Training Data</CardTitle>
        </div>
        <CardDescription>
          Use your trained LoRA to generate additional training images
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Prompt Input */}
        <div className="space-y-2">
          <Label htmlFor="synth-prompt">Prompt</Label>
          <Textarea
            id="synth-prompt"
            value={prompt}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setPrompt(e.target.value)}
            placeholder={`A photo of ${character.trigger_word}...`}
            rows={2}
          />
          <p className="text-xs text-muted-foreground">
            Include <code className="text-accent">{character.trigger_word}</code> to activate the character's likeness
          </p>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Label htmlFor="num-images" className="whitespace-nowrap">Images:</Label>
            <select
              id="num-images"
              className="h-9 rounded-md border border-border bg-input px-3 py-2 text-sm"
              value={numImages}
              onChange={(e) => setNumImages(parseInt(e.target.value))}
            >
              <option value={1}>1</option>
              <option value={2}>2</option>
              <option value={4}>4</option>
              <option value={8}>8</option>
            </select>
          </div>
          <Button
            onClick={handleGenerate}
            disabled={isGenerating || !prompt.trim()}
          >
            {isGenerating ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Wand2 className="mr-2 h-4 w-4" />
                Generate
              </>
            )}
          </Button>
        </div>

        {/* Generation Progress */}
        {isGenerating && currentJob && (
          <div className="bg-muted rounded-lg p-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                {currentJob.status === 'running' ? 'Generating images...' : 'Queued...'}
              </span>
              <span className="text-foreground">{Math.round(currentJob.progress)}%</span>
            </div>
            <div className="mt-2 h-2 bg-background rounded-full overflow-hidden">
              <div
                className="h-full bg-accent transition-all duration-300"
                style={{ width: `${currentJob.progress}%` }}
              />
            </div>
          </div>
        )}

        {/* Staged Images */}
        {stagedImages.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label>Staging Area ({stagedImages.filter(i => !i.kept).length} pending)</Label>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={handleKeepAll}>
                  <Check className="mr-2 h-4 w-4" />
                  Keep All
                </Button>
                <Button variant="ghost" size="sm" onClick={handleClearAll}>
                  <Trash2 className="mr-2 h-4 w-4" />
                  Clear All
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {stagedImages.map((image, index) => (
                <div
                  key={index}
                  className={`relative group aspect-square rounded-lg overflow-hidden bg-muted ${
                    image.kept ? 'ring-2 ring-success' : ''
                  }`}
                >
                  <img
                    src={image.url}
                    alt={`Generated ${index + 1}`}
                    className="w-full h-full object-cover"
                  />

                  {/* Overlay */}
                  {!image.kept && (
                    <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                      <Button
                        size="icon"
                        className="h-10 w-10 bg-success hover:bg-success/90"
                        disabled={image.saving}
                        onClick={() => handleKeepImage(index)}
                      >
                        {image.saving ? (
                          <Loader2 className="h-5 w-5 animate-spin" />
                        ) : (
                          <Check className="h-5 w-5" />
                        )}
                      </Button>
                      <Button
                        variant="destructive"
                        size="icon"
                        className="h-10 w-10"
                        onClick={() => handleDiscardImage(index)}
                      >
                        <X className="h-5 w-5" />
                      </Button>
                    </div>
                  )}

                  {/* Kept badge */}
                  {image.kept && (
                    <div className="absolute top-2 right-2 bg-success text-white px-2 py-1 rounded text-xs font-medium">
                      Saved
                    </div>
                  )}
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Click the checkmark to add an image to your training dataset, or X to discard it.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
