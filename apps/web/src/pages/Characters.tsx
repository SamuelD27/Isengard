import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Upload, Trash2, Zap, Image as ImageIcon, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, Character } from '@/lib/api'

export default function CharactersPage() {
  const queryClient = useQueryClient()
  const [isCreating, setIsCreating] = useState(false)
  const [newCharacter, setNewCharacter] = useState({
    name: '',
    description: '',
    trigger_word: '',
  })

  const { data: characters = [], isLoading } = useQuery({
    queryKey: ['characters'],
    queryFn: api.listCharacters,
  })

  const createMutation = useMutation({
    mutationFn: api.createCharacter,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['characters'] })
      setIsCreating(false)
      setNewCharacter({ name: '', description: '', trigger_word: '' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: api.deleteCharacter,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['characters'] })
    },
  })

  const handleCreate = () => {
    if (newCharacter.name && newCharacter.trigger_word) {
      createMutation.mutate(newCharacter)
    }
  }

  const handleFileUpload = async (characterId: string, e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      try {
        await api.uploadImages(characterId, e.target.files)
        queryClient.invalidateQueries({ queryKey: ['characters'] })
      } catch (error) {
        console.error('Upload failed:', error)
      }
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-6 w-6 border-2 border-accent border-t-transparent" />
      </div>
    )
  }

  return (
    <div className="space-y-6 fade-in">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">
            Manage identities for LoRA training
          </p>
        </div>
        <Button onClick={() => setIsCreating(true)} size="sm">
          <Plus className="mr-2 h-4 w-4" />
          New Character
        </Button>
      </div>

      {/* Create Character Modal */}
      {isCreating && (
        <Card className="border-accent/30">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>Create Character</CardTitle>
              <CardDescription>Define a new identity for training</CardDescription>
            </div>
            <Button variant="ghost" size="icon" onClick={() => setIsCreating(false)}>
              <X className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  placeholder="e.g., Sarah"
                  value={newCharacter.name}
                  onChange={(e) => setNewCharacter({ ...newCharacter, name: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="trigger">Trigger Word</Label>
                <Input
                  id="trigger"
                  placeholder="e.g., ohwx woman"
                  value={newCharacter.trigger_word}
                  onChange={(e) => setNewCharacter({ ...newCharacter, trigger_word: e.target.value })}
                />
                <p className="text-xs text-muted-foreground">Used in prompts to activate the LoRA</p>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description (optional)</Label>
              <Input
                id="description"
                placeholder="Brief description"
                value={newCharacter.description}
                onChange={(e) => setNewCharacter({ ...newCharacter, description: e.target.value })}
              />
            </div>
          </CardContent>
          <CardFooter className="flex justify-end gap-2 border-t border-border pt-5">
            <Button variant="outline" onClick={() => setIsCreating(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create'}
            </Button>
          </CardFooter>
        </Card>
      )}

      {/* Character Grid */}
      {characters.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <div className="rounded-full bg-muted p-4 mb-4">
              <Plus className="h-6 w-6 text-muted-foreground" />
            </div>
            <h3 className="font-medium text-foreground mb-2">No characters yet</h3>
            <p className="text-sm text-muted-foreground mb-4 max-w-sm">
              Create your first character to start training identity LoRAs
            </p>
            <Button onClick={() => setIsCreating(true)} size="sm">
              <Plus className="mr-2 h-4 w-4" />
              Create Character
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {characters.map((character) => (
            <CharacterCard
              key={character.id}
              character={character}
              onDelete={() => deleteMutation.mutate(character.id)}
              onUpload={(e) => handleFileUpload(character.id, e)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

interface CharacterCardProps {
  character: Character
  onDelete: () => void
  onUpload: (e: React.ChangeEvent<HTMLInputElement>) => void
}

function CharacterCard({ character, onDelete, onUpload }: CharacterCardProps) {
  return (
    <Card className="group hover:border-border-hover transition-colors">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <CardTitle className="truncate">{character.name}</CardTitle>
            <div className="flex items-center gap-2 mt-1.5">
              <code className="text-xs bg-muted px-1.5 py-0.5 rounded text-accent font-mono">
                {character.trigger_word}
              </code>
              {character.lora_path && (
                <span className="status-badge status-success">Trained</span>
              )}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pb-3">
        {character.description && (
          <p className="text-sm text-muted-foreground mb-3 line-clamp-2">
            {character.description}
          </p>
        )}
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <ImageIcon className="h-4 w-4" />
          <span>{character.image_count} images</span>
        </div>
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
        >
          <Zap className="mr-2 h-3.5 w-3.5" />
          Train
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="text-muted-foreground hover:text-destructive"
          onClick={onDelete}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </CardFooter>
    </Card>
  )
}
