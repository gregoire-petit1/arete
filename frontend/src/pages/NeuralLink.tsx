import { useState, useRef, useEffect } from 'react';
import { useMutation } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Send,
  Brain,
  Database,
  Loader2,
  MessageSquare,
  Sparkles,
  AlertTriangle,
  Target,
  Activity,
  Dumbbell,
  TrendingUp,
  Clock,
  Zap,
  CheckCircle,
  Info,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { ragApi } from '@/lib/api';
import { useSettings } from '@/contexts';
import type { RAGResponse, RAGSessionPlan, RAGExerciseInfo, RAGAnalysis, RAGGeneral } from '@/types';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  ragResponse?: RAGResponse;
  timestamp: Date;
}

const SYSTEM_PROMPTS = [
  'INITIALIZING NEURAL LINK...',
  'CONNECTING TO CHROMADB...',
  'LOADING KNOWLEDGE BASE...',
  'LINK ESTABLISHED.',
];

export function NeuralLinkPage() {
  const { settings } = useSettings();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [bootSequence, setBootSequence] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const displayName = settings?.display_name ?? 'HUNTER';

  // Boot sequence animation
  useEffect(() => {
    if (bootSequence < SYSTEM_PROMPTS.length) {
      const timer = setTimeout(() => {
        setBootSequence((prev) => prev + 1);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [bootSequence]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // Query mutation
  const queryMutation = useMutation({
    mutationFn: async (question: string): Promise<RAGResponse> => {
      return ragApi.query({ query: question });
    },
    onMutate: (question) => {
      // Add user message immediately
      const userMessage: Message = {
        id: Date.now().toString(),
        role: 'user',
        content: question,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMessage]);
      setInput('');
      setIsTyping(true);
    },
    onSuccess: (data) => {
      // Format response text from RAG data
      const responseText = formatRAGResponse(data);
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: responseText,
        ragResponse: data,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
      setIsTyping(false);
    },
    onError: (error) => {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `[ERREUR SYSTÈME] ${error.message}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      setIsTyping(false);
    },
  });

  // Format RAG response into readable text (used for typing animation)
  const formatRAGResponse = (data: RAGResponse): string => {
    // Just return a simple indicator - the actual formatting is in AssistantMessage
    switch (data.type) {
      case 'session_plan':
        return `[SESSION] ${data.titre}`;
      case 'exercise_info':
        return `[EXERCISE] ${data.exercice}`;
      case 'analysis':
        return `[ANALYSIS] ${data.titre}`;
      case 'general':
      default:
        return data.reponse || 'Réponse générée';
    }
  };

  const handleSend = () => {
    if (!input.trim() || queryMutation.isPending) return;
    queryMutation.mutate(input.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const bootComplete = bootSequence >= SYSTEM_PROMPTS.length;

  return (
    <div className="min-h-screen bg-void flex flex-col">
      {/* Header */}
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-panel mx-2 sm:mx-4 mb-0 px-3 py-3 sm:p-4 flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <Brain className="w-6 h-6 text-neon-purple" />
          <h1 className="text-base sm:text-xl font-display font-bold text-neon-purple tracking-wider">
            NEURAL LINK
          </h1>
        </div>
        <div className="hidden sm:flex items-center gap-2 text-xs font-mono text-text-muted">
          <Database className="w-4 h-4" />
          <span>ChromaDB Connected</span>
          <div className="w-2 h-2 rounded-full bg-success-green animate-pulse" />
        </div>
      </motion.header>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto px-2 py-3 sm:p-4 space-y-4 pb-2">
        {/* Boot Sequence */}
        <AnimatePresence>
          {!bootComplete && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="space-y-2"
            >
              {SYSTEM_PROMPTS.slice(0, bootSequence).map((prompt, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="text-xs font-mono text-neon-cyan"
                >
                  {'>'} {prompt}
                </motion.div>
              ))}
              {bootSequence < SYSTEM_PROMPTS.length && (
                <span className="inline-block w-2 h-4 bg-neon-cyan animate-pulse" />
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Welcome Message */}
        {bootComplete && messages.length === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="max-w-2xl mx-auto text-center py-8 sm:py-16 px-2"
          >
            <Sparkles className="w-12 h-12 text-neon-purple mx-auto mb-4" />
            <h2 className="text-lg sm:text-xl font-display text-text-primary mb-2">
              BIENVENUE, {displayName.toUpperCase()}
            </h2>
            <p className="text-sm text-text-muted font-mono mb-6">
              Posez-moi des questions sur vos entraînements, performances, et récupération.
              <br />
              Je puise dans votre historique pour vous donner des réponses personnalisées.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTED_QUESTIONS.map((q, i) => (
                <button
                  key={i}
                  onClick={() => {
                    setInput(q);
                    inputRef.current?.focus();
                  }}
                  className={cn(
                    'px-3 py-1.5 rounded text-xs font-mono',
                    'bg-neon-purple/10 border border-neon-purple/30 text-neon-purple',
                    'hover:bg-neon-purple/20 transition-all'
                  )}
                >
                  {q}
                </button>
              ))}
            </div>
          </motion.div>
        )}

        {/* Messages */}
        <AnimatePresence>
          {messages.map((message) => (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={cn(
                'max-w-[85vw] sm:max-w-3xl',
                message.role === 'user' ? 'ml-auto' : 'mr-auto'
              )}
            >
              {message.role === 'user' ? (
                <UserMessage content={message.content} />
              ) : (
                <AssistantMessage content={message.content} ragResponse={message.ragResponse} />
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Typing Indicator */}
        {isTyping && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center gap-2 text-text-muted text-sm font-mono"
          >
            <Loader2 className="w-4 h-4 animate-spin text-neon-purple" />
            <span>SYSTÈME ANALYSE EN COURS</span>
            <TypingDots />
          </motion.div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="sticky bottom-0 px-2 py-2 sm:p-4 bg-void/80 backdrop-blur-sm safe-bottom">
        <div
          className={cn(
            'glass-panel p-2 flex items-center gap-2',
            'border-neon-purple/30 focus-within:border-neon-purple/60'
          )}
        >
          <MessageSquare className="w-5 h-5 text-text-muted ml-2" />
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Posez votre question au système..."
            disabled={!bootComplete || queryMutation.isPending}
            className={cn(
              'flex-1 bg-transparent border-none outline-none',
              'text-text-primary font-mono text-sm',
              'placeholder:text-text-muted',
              'disabled:opacity-50'
            )}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || !bootComplete || queryMutation.isPending}
            className={cn(
              'p-2 rounded transition-all',
              'bg-neon-purple/20 text-neon-purple',
              'hover:bg-neon-purple/30',
              'disabled:opacity-30 disabled:cursor-not-allowed'
            )}
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
        <p className="text-[10px] text-text-muted text-center mt-2 font-mono">
          NEURAL LINK v1.0 │ Powered by Groq LLaMA │ RAG: ChromaDB
        </p>
      </div>
    </div>
  );
}

function UserMessage({ content }: { content: string }) {
  return (
    <div
      className={cn(
        'p-3 rounded-lg',
        'bg-neon-cyan/10 border border-neon-cyan/30',
        'text-text-primary text-sm font-mono'
      )}
    >
      {content}
    </div>
  );
}

function AssistantMessage({
  content,
  ragResponse,
}: {
  content: string;
  ragResponse?: RAGResponse;
}) {
  const [isComplete, setIsComplete] = useState(false);

  // Quick animation to reveal content
  useEffect(() => {
    const timer = setTimeout(() => setIsComplete(true), 300);
    return () => clearTimeout(timer);
  }, []);

  const sources = ragResponse?._metadata?.sources_retrieved || [];
  const warnings = ragResponse?.type === 'session_plan' ? ragResponse.avertissements || [] : [];

  return (
    <div className="space-y-3">
      <div
        className={cn(
          'p-4 rounded-lg',
          'bg-neon-purple/10 border border-neon-purple/30'
        )}
      >
        <div className="flex items-center gap-2 mb-3">
          <Brain className="w-4 h-4 text-neon-purple" />
          <span className="text-xs font-mono text-neon-purple uppercase">Système</span>
          {ragResponse?.type === 'session_plan' && ragResponse.charge_prevue && (
            <span className={cn(
              'ml-auto px-2 py-0.5 rounded text-[10px] font-mono',
              ragResponse.charge_prevue === 'légère' && 'bg-success-green/20 text-success-green',
              ragResponse.charge_prevue === 'modérée' && 'bg-neon-cyan/20 text-neon-cyan',
              ragResponse.charge_prevue === 'élevée' && 'bg-warning-orange/20 text-warning-orange',
              ragResponse.charge_prevue === 'intense' && 'bg-danger-red/20 text-danger-red',
            )}>
              <Activity className="w-3 h-3 inline mr-1" />
              {ragResponse.charge_prevue.toUpperCase()}
            </span>
          )}
        </div>
        
        {/* Render based on response type */}
        {ragResponse && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3 }}
          >
            {ragResponse.type === 'session_plan' && <SessionPlanView data={ragResponse} />}
            {ragResponse.type === 'exercise_info' && <ExerciseInfoView data={ragResponse} />}
            {ragResponse.type === 'analysis' && <AnalysisView data={ragResponse} />}
            {ragResponse.type === 'general' && <GeneralView data={ragResponse} />}
            {!ragResponse.type && <GeneralView data={{ type: 'general', reponse: content, points_cles: [], sources_utilisees: [] }} />}
          </motion.div>
        )}
        
        {!ragResponse && (
          <div className="text-sm text-text-primary font-mono">{content}</div>
        )}
      </div>

      {/* Warnings */}
      {isComplete && warnings.length > 0 && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className="p-3 rounded bg-warning-orange/10 border border-warning-orange/30"
        >
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="w-4 h-4 text-warning-orange" />
            <span className="text-xs font-mono text-warning-orange uppercase">Avertissements</span>
          </div>
          <ul className="space-y-1">
            {warnings.map((warning, i) => (
              <li key={i} className="text-xs font-mono text-text-muted">
                • {warning}
              </li>
            ))}
          </ul>
        </motion.div>
      )}

      {/* Sources */}
      {isComplete && sources.length > 0 && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className="pl-4 border-l-2 border-text-muted/20"
        >
          <p className="text-xs font-mono text-text-muted mb-2 uppercase">Sources consultées:</p>
          <div className="space-y-1">
            {sources.map((source, i) => (
              <div
                key={i}
                className={cn(
                  'flex items-center gap-2 text-xs font-mono overflow-hidden',
                  'text-text-muted hover:text-neon-cyan transition-colors cursor-pointer'
                )}
              >
                <Target className="w-3 h-3" />
                <span className="text-neon-cyan truncate">{source.id}</span>
                <span className="text-text-muted/50">
                  [{source.collection}]
                </span>
                <span className="text-text-muted/50">
                  (relevance: {(source.relevance * 100).toFixed(0)}%)
                </span>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}

// Session Plan View Component
function SessionPlanView({ data }: { data: RAGSessionPlan }) {
  return (
    <div className="space-y-4">
        <h3 className="text-base sm:text-lg font-display text-text-primary">{data.titre}</h3>
      
      {/* Sections */}
      <div className="space-y-2">
        {data.sections?.map((section, i) => (
          <div key={i} className="flex items-start gap-3 p-2 rounded bg-void/50">
            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-neon-purple/20 flex items-center justify-center">
              {i === 0 && <Zap className="w-3 h-3 text-neon-cyan" />}
              {i === 1 && <Activity className="w-3 h-3 text-neon-purple" />}
              {i === 2 && <Clock className="w-3 h-3 text-success-green" />}
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-neon-cyan uppercase">{section.nom}</span>
                <span className="text-xs font-mono text-text-muted">{section.duree}</span>
              </div>
              <p className="text-sm text-text-primary mt-1">{section.contenu}</p>
            </div>
          </div>
        ))}
      </div>
      
      {/* Targets */}
      {data.cibles && (
        <div className="flex flex-wrap gap-3 pt-2 border-t border-text-muted/20">
          {data.cibles.fc && (
            <span className="px-2 py-1 rounded text-xs font-mono bg-danger-red/10 text-danger-red">
              ❤️ {data.cibles.fc}
            </span>
          )}
          {data.cibles.allure && (
            <span className="px-2 py-1 rounded text-xs font-mono bg-neon-cyan/10 text-neon-cyan">
              🏃 {data.cibles.allure}
            </span>
          )}
          {data.cibles.rpe && (
            <span className="px-2 py-1 rounded text-xs font-mono bg-warning-orange/10 text-warning-orange">
              💪 RPE {data.cibles.rpe}
            </span>
          )}
        </div>
      )}
      
      {/* Justification */}
      {data.justification && (
        <p className="text-xs text-text-muted italic border-l-2 border-neon-purple/30 pl-3">
          {data.justification}
        </p>
      )}
    </div>
  );
}

// Exercise Info View Component
function ExerciseInfoView({ data }: { data: RAGExerciseInfo }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Dumbbell className="w-5 h-5 text-neon-purple" />
        <h3 className="text-base sm:text-lg font-display text-text-primary">{data.exercice}</h3>
      </div>
      
      {/* Description */}
      {data.description && (
        <p className="text-sm text-text-primary">{data.description}</p>
      )}
      
      {/* Muscles */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="p-2 rounded bg-danger-red/10 border border-danger-red/20">
          <span className="text-xs font-mono text-danger-red uppercase block mb-1">Muscles Principaux</span>
          <div className="flex flex-wrap gap-1">
            {data.muscles_principaux?.map((muscle, i) => (
              <span key={i} className="px-2 py-0.5 rounded-full text-xs bg-danger-red/20 text-text-primary">
                {muscle}
              </span>
            ))}
          </div>
        </div>
        <div className="p-2 rounded bg-warning-orange/10 border border-warning-orange/20">
          <span className="text-xs font-mono text-warning-orange uppercase block mb-1">Muscles Secondaires</span>
          <div className="flex flex-wrap gap-1">
            {data.muscles_secondaires?.map((muscle, i) => (
              <span key={i} className="px-2 py-0.5 rounded-full text-xs bg-warning-orange/20 text-text-primary">
                {muscle}
              </span>
            ))}
          </div>
        </div>
      </div>
      
      {/* Conseils */}
      {data.conseils && data.conseils.length > 0 && (
        <div>
          <span className="text-xs font-mono text-neon-cyan uppercase">Conseils</span>
          <ul className="mt-1 space-y-1">
            {data.conseils.map((conseil, i) => (
              <li key={i} className="text-sm text-text-muted flex items-start gap-2">
                <CheckCircle className="w-3 h-3 text-success-green mt-1 flex-shrink-0" />
                {conseil}
              </li>
            ))}
          </ul>
        </div>
      )}
      
      {/* Variantes */}
      {data.variantes && data.variantes.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <span className="text-xs font-mono text-text-muted">Variantes:</span>
          {data.variantes.map((v, i) => (
            <span key={i} className="px-2 py-0.5 rounded text-xs bg-neon-purple/10 text-neon-purple">
              {v}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// Analysis View Component
function AnalysisView({ data }: { data: RAGAnalysis }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <TrendingUp className="w-5 h-5 text-neon-cyan" />
      <h3 className="text-base sm:text-lg font-display text-text-primary">{data.titre}</h3>
      </div>
      
      {/* Resume */}
      {data.resume && (
        <p className="text-sm text-text-primary bg-neon-cyan/5 p-3 rounded border-l-2 border-neon-cyan">
          {data.resume}
        </p>
      )}
      
      {/* Points clés */}
      {data.points_cles && data.points_cles.length > 0 && (
        <div className="grid gap-2">
          {data.points_cles.map((point, i) => (
            <div key={i} className={cn(
              'p-2 rounded flex items-center justify-between',
              point.interpretation === 'bon' && 'bg-success-green/10 border border-success-green/20',
              point.interpretation === 'attention' && 'bg-warning-orange/10 border border-warning-orange/20',
              point.interpretation === 'alerte' && 'bg-danger-red/10 border border-danger-red/20',
            )}>
              <span className="text-sm font-mono text-text-muted">{point.label}</span>
              <span className={cn(
                'text-sm font-bold',
                point.interpretation === 'bon' && 'text-success-green',
                point.interpretation === 'attention' && 'text-warning-orange',
                point.interpretation === 'alerte' && 'text-danger-red',
              )}>
                {point.valeur}
              </span>
            </div>
          ))}
        </div>
      )}
      
      {/* Recommandations */}
      {data.recommandations && data.recommandations.length > 0 && (
        <div>
          <span className="text-xs font-mono text-neon-purple uppercase">Recommandations</span>
          <ul className="mt-2 space-y-1">
            {data.recommandations.map((rec, i) => (
              <li key={i} className="text-sm text-text-primary flex items-start gap-2">
                <span className="text-neon-purple">→</span>
                {rec}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// General View Component
function GeneralView({ data }: { data: RAGGeneral }) {
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2">
        <Info className="w-4 h-4 text-neon-cyan mt-0.5 flex-shrink-0" />
        <p className="text-sm text-text-primary whitespace-pre-wrap">{data.reponse}</p>
      </div>
      
      {data.points_cles && data.points_cles.length > 0 && (
        <ul className="space-y-1 pl-6">
          {data.points_cles.map((point, i) => (
            <li key={i} className="text-sm text-text-muted list-disc">
              {point}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TypingDots() {
  return (
    <span className="inline-flex gap-1">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
          className="w-1.5 h-1.5 bg-neon-purple rounded-full"
        />
      ))}
    </span>
  );
}

const SUGGESTED_QUESTIONS = [
  "Comment s'est passée ma semaine d'entraînement ?",
  'Suis-je en forme pour une séance intense ?',
  'Quel est mon état de récupération ?',
  'Analyse ma charge de travail récente',
];
