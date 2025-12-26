import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Upload, Trash2, Zap, Image as ImageIcon } from 'lucide-react'
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
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Characters</h1>
          <p className="text-muted-foreground">
            Manage your identity characters for LoRA training
          </p>
        </div>
        <Button onClick={() => setIsCreating(true)}>
          <Plus className="mr-2 h-4 w-4" />
          New Character
        </Button>
      </div>

      {/* Create Character Form */}
      {isCreating && (
        <Card>
          <CardHeader>
            <CardTitle>Create New Character</CardTitle>
            <CardDescription>
              Define a new identity for LoRA training
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="name">Character Name</Label>
                <Input
                  id="name"
                  placeholder="e.g., Sarah"
                  value={newCharacter.name}
                  onChange={(e) => setNewCharacter({ ...newCharacter, name: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="trigger">
                  Trigger Word
                  <span className="ml-2 text-xs text-muted-foreground">
                    (used in prompts to activate the LoRA)
                  </span>
                </Label>
                <Input
                  id="trigger"
                  placeholder="e.g., ohwx woman"
                  value={newCharacter.trigger_word}
                  onChange={(e) => setNewCharacter({ ...newCharacter, trigger_word: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description (optional)</Label>
              <Input
                id="description"
                placeholder="Brief description of the character"
                value={newCharacter.description}
                onChange={(e) => setNewCharacter({ ...newCharacter, description: e.target.value })}
              />
            </div>
          </CardContent>
          <CardFooter className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setIsCreating(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Character'}
            </Button>
          </CardFooter>
        </Card>
      )}

      {/* Character Grid */}
      {characters.length === 0 ? (
        <Card className="flex flex-col items-center justify-center p-12 text-center">
          <div className="rounded-full bg-muted p-4 mb-4">
            <Plus className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="font-semibold text-lg mb-2">No characters yet</h3>
          <p className="text-muted-foreground mb-4">
            Create your first character to start training identity LoRAs
          </p>
          <Button onClick={() => setIsCreating(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Create Character
          </Button>
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
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
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle>{character.name}</CardTitle>
            <CardDescription className="mt-1">
              Trigger: <code className="bg-muted px-1 rounded">{character.trigger_word}</code>
            </CardDescription>
          </div>
          {character.lora_path && (
            <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded-full">
              Trained
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {character.description && (
          <p className="text-sm text-muted-foreground mb-4">{character.description}</p>
        )}
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-1">
            <ImageIcon className="h-4 w-4 text-muted-foreground" />
            <span>{character.image_count} images</span>
          </div>
        </div>
      </CardContent>
      <CardFooter className="flex gap-2">
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
        <Button variant="outline" size="sm" disabled={character.image_count === 0}>
          <Zap className="mr-2 h-4 w-4" />
          Train
        </Button>
        <Button variant="ghost" size="icon" className="ml-auto text-destructive" onClick={onDelete}>
          <Trash2 className="h-4 w-4" />
        </Button>
      </CardFooter>
    </Card>
  )
}
