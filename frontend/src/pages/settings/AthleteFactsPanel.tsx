import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Pencil, Trash2, UserRound, X } from 'lucide-react';
import { Button, Input, Panel, Select } from '@/components/ui';
import { athleteFactsApi } from '@/lib/api';
import { parseLocalDate } from '@/lib/dates';
import { FACT_KIND_LABEL } from '@/lib/fr';
import { qk } from '@/lib/queryKeys';
import { cn, readableError } from '@/lib/utils';
import type { AthleteFact, FactKind } from '@/types';

const MAX_TEXT = 300;
const KINDS = Object.keys(FACT_KIND_LABEL) as FactKind[];

interface FactActions {
  busyId: number | null;
  onSave: (fact: AthleteFact, text: string) => void;
  onToggle: (fact: AthleteFact) => void;
  onDelete: (fact: AthleteFact) => void;
}

function FactRow({ fact, busyId, onSave, onToggle, onDelete }: FactActions & { fact: AthleteFact }) {
  const [draft, setDraft] = useState<string | null>(null);
  const resolved = fact.status === 'resolved';
  const busy = busyId === fact.id;
  const save = () => {
    const text = draft?.trim();
    if (text && text !== fact.text) onSave(fact, text);
    setDraft(null);
  };

  return (
    <li
      data-status={fact.status}
      className={cn('rounded border border-text-muted/20 p-3 space-y-2', resolved && 'opacity-50')}
    >
      <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono">
        <span className="text-neon-purple uppercase">{FACT_KIND_LABEL[fact.kind] ?? fact.kind}</span>
        <span className="text-text-muted">
          depuis le {parseLocalDate(fact.since).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })}
        </span>
        <span
          className={cn(
            'px-1.5 py-0.5 rounded border',
            fact.source === 'coach'
              ? 'border-neon-cyan/30 text-neon-cyan'
              : 'border-neon-gold/30 text-neon-gold'
          )}
        >
          {fact.source === 'coach' ? 'coach' : 'toi'}
        </span>
        {resolved && <span className="text-text-muted">résolu</span>}
      </div>
      {draft === null ? (
        <p className="text-sm text-text-primary break-words">{fact.text}</p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
          className="flex gap-2"
        >
          <Input
            autoFocus
            aria-label="Texte du fait"
            maxLength={MAX_TEXT}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="text-sm"
          />
          <Button type="submit" size="sm" aria-label="Enregistrer le fait">
            <Check className="size-3.5" />
          </Button>
          <Button variant="ghost" size="sm" aria-label="Annuler la modification" onClick={() => setDraft(null)}>
            <X className="size-3.5" />
          </Button>
        </form>
      )}
      <div className="flex justify-end gap-2">
        {draft === null && (
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => setDraft(fact.text)}>
            <Pencil className="size-3.5" /> Modifier
          </Button>
        )}
        <Button variant={resolved ? 'cyan' : 'green'} size="sm" disabled={busy} onClick={() => onToggle(fact)}>
          {resolved ? 'Réactiver' : 'Résolu'}
        </Button>
        <Button variant="ghost" size="sm" disabled={busy} aria-label="Supprimer le fait" onClick={() => onDelete(fact)}>
          <Trash2 className="size-3.5" />
        </Button>
      </div>
    </li>
  );
}

/** Active facts first, then resolved ones, dimmed; server order within each. */
export function FactList({ facts, ...actions }: FactActions & { facts: AthleteFact[] }) {
  const ordered = [
    ...facts.filter((f) => f.status === 'active'),
    ...facts.filter((f) => f.status !== 'active'),
  ];
  return (
    <ul className="space-y-2">
      {ordered.map((fact) => (
        <FactRow key={fact.id} fact={fact} {...actions} />
      ))}
    </ul>
  );
}

function AddFactForm() {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<FactKind>('injury');
  const [text, setText] = useState('');
  const add = useMutation({
    mutationFn: (fact: { kind: FactKind; text: string }) => athleteFactsApi.create(fact),
    onSuccess: () => {
      setText('');
      queryClient.invalidateQueries({ queryKey: qk.athleteFacts });
    },
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) add.mutate({ kind, text: text.trim() });
      }}
      className="space-y-2 border-t border-text-muted/10 pt-3"
    >
      <div className="flex flex-col sm:flex-row gap-2">
        <Select
          aria-label="Type de fait"
          value={kind}
          onChange={(e) => setKind(e.target.value as FactKind)}
          className="sm:w-40 text-sm"
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {FACT_KIND_LABEL[k]}
            </option>
          ))}
        </Select>
        <Input
          aria-label="Nouveau fait"
          maxLength={MAX_TEXT}
          placeholder="Tendinite d’Achille gauche, pas de côtes"
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="text-sm"
        />
        <Button type="submit" size="sm" loading={add.isPending} disabled={!text.trim()}>
          Ajouter
        </Button>
      </div>
      {add.isError && <p className="text-xs text-danger-red">{readableError(add.error)}</p>}
    </form>
  );
}

/** The durable facts the coach reads every turn; editable at once, apart from the form's save. */
export function AthleteFactsPanel() {
  const queryClient = useQueryClient();
  const facts = useQuery({ queryKey: qk.athleteFacts, queryFn: athleteFactsApi.list });
  const [busyId, setBusyId] = useState<number | null>(null);
  const settle = {
    onSettled: () => {
      setBusyId(null);
      queryClient.invalidateQueries({ queryKey: qk.athleteFacts });
    },
  };
  const update = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Parameters<typeof athleteFactsApi.update>[1] }) =>
      athleteFactsApi.update(id, patch),
    ...settle,
  });
  const remove = useMutation({ mutationFn: (id: number) => athleteFactsApi.remove(id), ...settle });
  const error = update.error ?? remove.error;

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <UserRound className="size-4 text-neon-purple" /> Ce que le coach sait de toi
        </span>
      }
    >
      <div className="space-y-3">
        <p className="text-xs text-text-muted">
          Blessures, contraintes et préférences que le coach garde en tête à chaque échange. Il en ajoute
          quand tu lui en parles ; tu peux les corriger ici.
        </p>
        {facts.isLoading && <p className="text-sm text-text-muted">Chargement…</p>}
        {facts.isError && <p className="text-sm text-danger-red">Faits indisponibles.</p>}
        {facts.data?.length === 0 && <p className="text-sm text-text-muted italic">Rien pour le moment.</p>}
        {facts.data && facts.data.length > 0 && (
          <FactList
            facts={facts.data}
            busyId={busyId}
            onSave={(fact, text) => {
              setBusyId(fact.id);
              update.mutate({ id: fact.id, patch: { text } });
            }}
            onToggle={(fact) => {
              setBusyId(fact.id);
              update.mutate({ id: fact.id, patch: { status: fact.status === 'active' ? 'resolved' : 'active' } });
            }}
            onDelete={(fact) => {
              setBusyId(fact.id);
              remove.mutate(fact.id);
            }}
          />
        )}
        {error && <p className="text-xs text-danger-red">{readableError(error)}</p>}
        <AddFactForm />
      </div>
    </Panel>
  );
}
