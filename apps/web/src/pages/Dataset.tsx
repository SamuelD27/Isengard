import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Database, Search, Image as ImageIcon, Loader2, X, Tag, FolderOpen, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'

interface DatasetViewImage {
  filename: string
  character_id: string
  character_name: string
  url: string
}

export default function DatasetPage() {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCharacter, setSelectedCharacter] = useState<string>('all')
  const [selectedImages, setSelectedImages] = useState<Set<string>>(new Set())

  // Fetch all characters
  const { data: characters = [], isLoading: charactersLoading } = useQuery({
    queryKey: ['characters'],
    queryFn: api.listCharacters,
  })

  // Fetch images for each character
  const { data: allImages = [], isLoading: imagesLoading } = useQuery({
    queryKey: ['all-dataset-images', characters.map((c: { id: string }) => c.id)],
    queryFn: async () => {
      const results: DatasetViewImage[] = []
      for (const char of characters) {
        try {
          const data = await api.listImages(char.id)
          for (const filename of data.images) {
            results.push({
              filename,
              character_id: char.id,
              character_name: char.name,
              url: `/api/characters/${char.id}/images/${filename}`,
            })
          }
        } catch (e) {
          console.error(`Failed to load images for ${char.id}`, e)
        }
      }
      return results
    },
    enabled: characters.length > 0,
  })

  // Filter images
  const filteredImages = useMemo(() => {
    return allImages.filter((img: DatasetViewImage) => {
      const matchesCharacter = selectedCharacter === 'all' || img.character_id === selectedCharacter
      const matchesSearch = !searchQuery ||
        img.filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
        img.character_name.toLowerCase().includes(searchQuery.toLowerCase())
      return matchesCharacter && matchesSearch
    })
  }, [allImages, selectedCharacter, searchQuery])

  // Bulk delete mutation
  const deleteMutation = useMutation({
    mutationFn: async (images: { characterId: string; filename: string }[]) => {
      for (const img of images) {
        await api.deleteImage(img.characterId, img.filename)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['all-dataset-images'] })
      queryClient.invalidateQueries({ queryKey: ['characters'] })
      setSelectedImages(new Set())
    },
  })

  const handleSelectImage = (key: string) => {
    const newSet = new Set(selectedImages)
    if (newSet.has(key)) {
      newSet.delete(key)
    } else {
      newSet.add(key)
    }
    setSelectedImages(newSet)
  }

  const handleSelectAll = () => {
    if (selectedImages.size === filteredImages.length) {
      setSelectedImages(new Set())
    } else {
      setSelectedImages(new Set(filteredImages.map((img: DatasetViewImage) => `${img.character_id}:${img.filename}`)))
    }
  }

  const handleBulkDelete = () => {
    const toDelete = Array.from(selectedImages).map(key => {
      const [characterId, filename] = key.split(':')
      return { characterId, filename }
    })
    if (confirm(`Delete ${toDelete.length} images? This cannot be undone.`)) {
      deleteMutation.mutate(toDelete)
    }
  }

  const isLoading = charactersLoading || imagesLoading
  const totalImages = allImages.length
  const totalCharacters = characters.filter((c: { image_count: number }) => c.image_count > 0).length

  return (
    <div className="space-y-6 fade-in">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
            <Database className="h-5 w-5" />
            Dataset Manager
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage training images across all characters
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span>{totalImages} images</span>
          <span>•</span>
          <span>{totalCharacters} characters</span>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            {/* Search */}
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search images..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>

            {/* Character Filter */}
            <div className="w-full md:w-48">
              <select
                className="flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
                value={selectedCharacter}
                onChange={(e) => setSelectedCharacter(e.target.value)}
              >
                <option value="all">All Characters</option>
                {characters.filter((c: { image_count: number }) => c.image_count > 0).map((char: { id: string; name: string; image_count: number }) => (
                  <option key={char.id} value={char.id}>
                    {char.name} ({char.image_count})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Bulk Actions */}
          {selectedImages.size > 0 && (
            <div className="flex items-center gap-4 mt-4 pt-4 border-t border-border">
              <span className="text-sm text-foreground">
                {selectedImages.size} selected
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelectedImages(new Set())}
              >
                <X className="mr-2 h-4 w-4" />
                Clear
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleBulkDelete}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="mr-2 h-4 w-4" />
                )}
                Delete Selected
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Image Grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : filteredImages.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <div className="rounded-full bg-muted p-4 mb-4">
              <ImageIcon className="h-8 w-8 text-muted-foreground" />
            </div>
            <h3 className="font-medium text-foreground mb-2">
              {allImages.length === 0 ? 'No images yet' : 'No matching images'}
            </h3>
            <p className="text-sm text-muted-foreground max-w-sm">
              {allImages.length === 0
                ? 'Upload images to your characters to see them here'
                : 'Try adjusting your search or filter criteria'
              }
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {/* Select All */}
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={handleSelectAll}
            >
              {selectedImages.size === filteredImages.length ? 'Deselect All' : 'Select All'}
            </Button>
            <span className="text-sm text-muted-foreground">
              Showing {filteredImages.length} of {totalImages} images
            </span>
          </div>

          {/* Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-3">
            {filteredImages.map((img: DatasetViewImage) => {
              const key = `${img.character_id}:${img.filename}`
              const isSelected = selectedImages.has(key)

              return (
                <div
                  key={key}
                  className={`relative group aspect-square rounded-lg overflow-hidden bg-muted cursor-pointer ${
                    isSelected ? 'ring-2 ring-accent' : ''
                  }`}
                  onClick={() => handleSelectImage(key)}
                >
                  <img
                    src={img.url}
                    alt={img.filename}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />

                  {/* Selection overlay */}
                  <div className={`absolute inset-0 transition-colors ${
                    isSelected ? 'bg-accent/20' : 'group-hover:bg-black/30'
                  }`}>
                    <div className={`absolute top-2 left-2 w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                      isSelected
                        ? 'bg-accent border-accent'
                        : 'border-white/70 group-hover:border-white'
                    }`}>
                      {isSelected && (
                        <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                  </div>

                  {/* Character badge */}
                  <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
                    <div className="flex items-center gap-1">
                      <Tag className="h-3 w-3 text-accent" />
                      <span className="text-xs text-white truncate">{img.character_name}</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Character Summary Cards */}
      {characters.filter((c: { image_count: number }) => c.image_count > 0).length > 0 && (
        <div className="space-y-4">
          <h2 className="text-base font-medium text-foreground flex items-center gap-2">
            <FolderOpen className="h-4 w-4" />
            Characters Overview
          </h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {characters.filter((c: { image_count: number }) => c.image_count > 0).map((char: { id: string; name: string; trigger_word: string; image_count: number; lora_path: string | null }) => (
              <Card key={char.id} className="hover:border-border-hover transition-colors">
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-medium text-foreground">{char.name}</h3>
                      <p className="text-sm text-muted-foreground">
                        <code className="text-xs text-accent">{char.trigger_word}</code>
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-semibold text-foreground">{char.image_count}</p>
                      <p className="text-xs text-muted-foreground">images</p>
                    </div>
                  </div>
                  {char.lora_path && (
                    <div className="mt-3 pt-3 border-t border-border">
                      <span className="status-badge status-success">LoRA Trained</span>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
