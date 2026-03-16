import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Flex,
  HStack,
  Text,
  useToast,
} from '@chakra-ui/react';
import { keyframes } from '@emotion/react';
import { productsApi } from '../../api/products';
import { aiAssistantApi } from '../../api/ai-assistant';
import { evidencesApi } from '../../api/evidences';
import type { Product, PipelineResult, PipelineQuestion, ChecklistItem, EvidencesPreview, ReferenceItem } from './types';

import StepDiagnostico from './components/StepDiagnostico';
import StepPaciente from './components/StepPaciente';
import StepGeracaoIA from './components/StepGeracaoIA';
import StepRevisao from './components/StepRevisao';

const pulseRing = keyframes`
  0% { transform: scale(1); opacity: 0.8; }
  50% { transform: scale(1.15); opacity: 0.4; }
  100% { transform: scale(1); opacity: 0.8; }
`;

const STEPS = [
  { title: 'Diagnóstico', description: 'CID e quadro clínico' },
  { title: 'Paciente & OPME', description: 'Dados e material' },
  { title: 'Geração IA', description: 'Justificativa inteligente' },
  { title: 'Revisão', description: 'Download e assinatura' },
];

function StepperProgress({ activeStep, onStepClick }: { activeStep: number; onStepClick: (i: number) => void }) {
  return (
    <Flex justify="center" mb={10}>
      <HStack gap={0} align="flex-start">
        {STEPS.map((step, i) => {
          const isDone = i < activeStep;
          const isActive = i === activeStep;
          return (
            <Flex key={i} align="center">
              <Flex
                direction="column" align="center" minW="100px"
                cursor={isDone ? 'pointer' : 'default'}
                onClick={() => isDone && onStepClick(i)}
                role={isDone ? 'button' : undefined}
              >
                {/* Circle */}
                <Flex
                  w="40px" h="40px" borderRadius="full" align="center" justify="center"
                  position="relative"
                  border="2px solid"
                  borderColor={isDone ? 'brand.600' : isActive ? 'brand.500' : 'border.muted'}
                  bg={isDone ? 'brand.600' : isActive ? 'brand.50' : 'surface'}
                  color={isDone ? 'white' : isActive ? 'brand.700' : 'text.subtle'}
                  transition="all 0.5s cubic-bezier(0.65, 0.05, 0, 1)"
                  fontWeight="700" fontSize="sm"
                >
                  {isDone ? (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <path d="M3 8L6.5 11.5L13 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  ) : (
                    <Text fontSize="sm">{i + 1}</Text>
                  )}
                  {/* Active pulse ring */}
                  {isActive && (
                    <Box
                      position="absolute" inset="-5px" borderRadius="full"
                      border="2px solid" borderColor="brand.300"
                      sx={{ animation: `${pulseRing} 2s ease-in-out infinite` }}
                    />
                  )}
                </Flex>
                {/* Labels */}
                <Text
                  fontSize="xs" fontWeight={isActive ? '700' : isDone ? '600' : '400'}
                  color={isActive ? 'brand.600' : isDone ? 'brand.600' : 'text.subtle'}
                  mt={2} textAlign="center" transition="all 0.3s"
                >
                  {step.title}
                </Text>
                <Text
                  fontSize="2xs"
                  color={isActive ? 'text.muted' : 'text.subtle'}
                  textAlign="center" transition="all 0.3s"
                >
                  {step.description}
                </Text>
              </Flex>
              {/* Connector line */}
              {i < STEPS.length - 1 && (
                <Box position="relative" mt="-20px">
                  {/* Background line */}
                  <Box w="60px" h="2px" bg="border.muted" borderRadius="full" />
                  {/* Fill line */}
                  <Box
                    position="absolute" top={0} left={0} h="2px" borderRadius="full"
                    bg="brand.600"
                    w={isDone ? '100%' : '0%'}
                    transition="width 0.6s cubic-bezier(0.65, 0.05, 0, 1)"
                  />
                </Box>
              )}
            </Flex>
          );
        })}
      </HStack>
    </Flex>
  );
}

export default function ReportCreate() {
  const [activeStep, setActiveStep] = useState(0);
  const navigate = useNavigate();
  const toast = useToast();

  // Step 1: Identificação
  const [pacienteNome, setPacienteNome] = useState('');
  const [cid, setCid] = useState('');
  const [diagnostico, setDiagnostico] = useState('');
  const [surgeryDescription, setSurgeryDescription] = useState('');
  const [healthPlan, setHealthPlan] = useState('');
  const [especialidade, setEspecialidade] = useState('');

  // Evidences preview (PubMed)
  const [evidencesPreview, setEvidencesPreview] = useState<EvidencesPreview | null>(null);
  const [evidencesLoading, setEvidencesLoading] = useState(false);
  const evidencesDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Step 2: Material
  const [products, setProducts] = useState<Product[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const productDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Quick product registration
  const [showQuickRegister, setShowQuickRegister] = useState(false);
  const [quickName, setQuickName] = useState('');
  const [quickAnvisa, setQuickAnvisa] = useState('');
  const [quickFabricante, setQuickFabricante] = useState('');
  const [quickTuss, setQuickTuss] = useState('');
  const [savingProduct, setSavingProduct] = useState(false);

  // Step 3: IA
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineStep, setPipelineStep] = useState('');
  const [pipelineMessages, setPipelineMessages] = useState<string[]>([]);
  const [textRevealing, setTextRevealing] = useState(false);
  const [pipelineResult, setPipelineResult] = useState<PipelineResult | null>(null);
  const [questions, setQuestions] = useState<PipelineQuestion[]>([]);
  const [questionAnswers, setQuestionAnswers] = useState<Record<string, string>>({});
  const [justificativa, setJustificativa] = useState('');
  const [justificativaOriginal, setJustificativaOriginal] = useState('');
  const [sessionId, setSessionId] = useState('');

  // Step 4: Checklist (reativo)
  const [checklist, setChecklist] = useState<Record<string, boolean | ChecklistItem>>({});
  const [approved, setApproved] = useState(false);
  const [auditSummary, setAuditSummary] = useState<Record<string, unknown> | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // --- Callbacks ---

  const fetchEvidencesPreview = useCallback(async (cidValue: string) => {
    if (!cidValue || cidValue.trim().length < 3) {
      setEvidencesPreview(null);
      return;
    }
    setEvidencesLoading(true);
    try {
      const result = await evidencesApi.preview(cidValue.trim());
      setEvidencesPreview(result);
    } catch {
      setEvidencesPreview(null);
    } finally {
      setEvidencesLoading(false);
    }
  }, []);

  const handleCidChange = useCallback((value: string) => {
    setCid(value);
    if (evidencesDebounceRef.current) clearTimeout(evidencesDebounceRef.current);
    evidencesDebounceRef.current = setTimeout(() => fetchEvidencesPreview(value), 500);
  }, [fetchEvidencesPreview]);

  const searchProducts = useCallback(async (q: string) => {
    setLoadingProducts(true);
    try {
      const res = await productsApi.list(q || undefined);
      setProducts(res.items || []);
    } catch {
      setProducts([]);
    } finally {
      setLoadingProducts(false);
    }
  }, []);

  const handleProductSearchChange = useCallback((value: string) => {
    setSearchQuery(value);
    if (productDebounceRef.current) clearTimeout(productDebounceRef.current);
    productDebounceRef.current = setTimeout(() => searchProducts(value), 300);
  }, [searchProducts]);

  useEffect(() => {
    searchProducts('');
  }, [searchProducts]);

  const handleSelectProduct = async (p: Product) => {
    if (p.source === 'anvisa' && p.id.startsWith('anvisa:')) {
      const registro = p.id.replace('anvisa:', '');
      try {
        const created = await productsApi.createFromAnvisa(registro);
        setSelectedProduct({
          ...p,
          id: created.id,
          source: 'catalog',
        });
        toast({ title: 'Produto importado da base ANVISA', status: 'success', duration: 2000 });
      } catch {
        toast({ title: 'Erro ao importar produto ANVISA', status: 'error' });
      }
    } else {
      setSelectedProduct(p);
    }
  };

  const handleQuickRegister = async () => {
    if (!quickName.trim()) {
      toast({ title: 'Informe o nome do material', status: 'warning' });
      return;
    }
    setSavingProduct(true);
    try {
      const created = await productsApi.create({
        nome: quickName.trim(),
        registro_anvisa: quickAnvisa.trim() || undefined,
        fabricante: quickFabricante.trim() || undefined,
        codigo_tuss_sugerido: quickTuss.trim() || undefined,
      });
      const newProduct: Product = {
        id: created.id,
        nome: created.nome,
        linha: '',
        descricao_tecnica: '',
        diferenciais_clinicos: '',
        codigo_tuss_sugerido: created.codigo_tuss_sugerido || '',
        registro_anvisa: created.registro_anvisa || '',
      };
      setSelectedProduct(newProduct);
      setShowQuickRegister(false);
      toast({ title: 'Produto cadastrado com sucesso', status: 'success' });
    } catch {
      toast({ title: 'Erro ao cadastrar produto', status: 'error' });
    } finally {
      setSavingProduct(false);
    }
  };

  const handlePipelineResult = (result: PipelineResult) => {
    setPipelineResult(result);
    setSessionId(result.session_id);
    if (result.step === 'questions' && result.questions) {
      setQuestions(result.questions);
    } else if (result.step === 'done') {
      const text = result.justificativa || '';
      setJustificativa(text);
      setJustificativaOriginal(text);
      setChecklist(result.checklist || {});
      setApproved(result.aprovado || false);
      if ((result as unknown as Record<string, unknown>).audit_summary) {
        setAuditSummary((result as unknown as Record<string, unknown>).audit_summary as Record<string, unknown>);
      }
    }
  };

  const startPipeline = async () => {
    if (!selectedProduct) return;
    setPipelineLoading(true);
    setPipelineStep('researching');
    setPipelineMessages([]);
    setActiveStep(2);

    aiAssistantApi.startReportStream(
      {
        product_id: selectedProduct.id,
        paciente_nome: pacienteNome,
        cid,
        diagnostico,
        surgery_description: surgeryDescription,
        health_plan: healthPlan,
        especialidade,
      },
      (step, message) => {
        setPipelineStep(step);
        if (message) setPipelineMessages((prev) => [...prev, message]);
      },
      (result) => {
        setPipelineLoading(false);
        setPipelineStep('');
        if (result.step === 'done' && result.justificativa) {
          setPipelineResult(result);
          setSessionId(result.session_id);
          setTextRevealing(true);
          setJustificativaOriginal(result.justificativa);
          setChecklist(result.checklist || {});
          setApproved(result.aprovado || false);
          if ((result as unknown as Record<string, unknown>).audit_summary) {
            setAuditSummary((result as unknown as Record<string, unknown>).audit_summary as Record<string, unknown>);
          }
        } else {
          handlePipelineResult(result);
        }
      },
      () => {
        toast({ title: 'Erro ao iniciar assistente', status: 'error' });
        setPipelineLoading(false);
        setPipelineStep('');
      },
    );
  };

  const handleNext = () => {
    if (activeStep === 0) {
      if (!cid || !diagnostico) {
        toast({ title: 'Preencha CID e Diagnóstico', status: 'warning' });
        return;
      }
    }
    if (activeStep === 1) {
      if (!pacienteNome) {
        toast({ title: 'Preencha o nome do paciente', status: 'warning' });
        return;
      }
      if (!selectedProduct) {
        toast({ title: 'Selecione ou cadastre um material OPME', status: 'warning' });
        return;
      }
      startPipeline();
      return;
    }
    setActiveStep(activeStep + 1);
  };

  const handleBack = () => setActiveStep(Math.max(0, activeStep - 1));

  const runQuickCheck = useCallback(async (text: string) => {
    try {
      const refs = (pipelineResult?.referencias || []).map((r) =>
        typeof r === 'string' ? r : (r as ReferenceItem).texto || ''
      );
      const res = await aiAssistantApi.quickCheck({
        justificativa_ia: text,
        diagnostico,
        falha_terapeutica: pipelineResult?.falha_terapeutica || '',
        risco_nao_realizacao: pipelineResult?.risco_nao_realizacao || '',
        base_legal_ans: pipelineResult?.base_legal || '',
        referencias_bib: refs,
      });
      setChecklist(res.checklist);
      setApproved(res.approved);
    } catch { /* silent */ }
  }, [diagnostico, pipelineResult]);

  const handleJustificativaChange = useCallback((text: string) => {
    setJustificativa(text);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runQuickCheck(text), 2000);
  }, [runQuickCheck]);

  const submitAnswers = async () => {
    setPipelineLoading(true);
    setPipelineStep('writing');
    setPipelineMessages([]);
    setQuestions([]);

    aiAssistantApi.answerStream(
      sessionId,
      questionAnswers,
      (step, message) => {
        setPipelineStep(step);
        if (message) setPipelineMessages((prev) => [...prev, message]);
      },
      (result) => {
        setPipelineLoading(false);
        setPipelineStep('');
        if (result.step === 'done' && result.justificativa) {
          setPipelineResult(result);
          setSessionId(result.session_id);
          setTextRevealing(true);
          setJustificativaOriginal(result.justificativa);
          setChecklist(result.checklist || {});
          setApproved(result.aprovado || false);
          if ((result as unknown as Record<string, unknown>).audit_summary) {
            setAuditSummary((result as unknown as Record<string, unknown>).audit_summary as Record<string, unknown>);
          }
        } else {
          handlePipelineResult(result);
        }
      },
      () => {
        toast({ title: 'Erro ao enviar respostas', status: 'error' });
        setPipelineLoading(false);
        setPipelineStep('');
      },
    );
  };

  const handleRegenerate = async () => {
    if (!sessionId) return;
    setPipelineLoading(true);
    try {
      const result = await aiAssistantApi.regenerate(
        sessionId,
        pipelineResult?.report_id || null,
        { justificativa_ajustada: justificativa }
      );
      handlePipelineResult(result);
      toast({ title: 'Relatório regenerado', status: 'success' });
    } catch {
      toast({ title: 'Erro ao regenerar', status: 'error' });
    } finally {
      setPipelineLoading(false);
    }
  };

  const goToReview = () => {
    if (pipelineResult?.report_id) {
      navigate(`/dashboard/reports/${pipelineResult.report_id}/review`);
    } else {
      toast({ title: 'Relatório ainda não foi salvo', status: 'warning' });
    }
  };

  const handleStepGeracaoNext = () => {
    if (justificativaOriginal && justificativa !== justificativaOriginal && pipelineResult?.report_id) {
      aiAssistantApi.saveEdit({
        report_id: pipelineResult.report_id,
        original_text: justificativaOriginal,
        edited_text: justificativa,
        especialidade: especialidade || undefined,
      }).catch(() => {});
    }
    setActiveStep(3);
  };

  return (
    <Box>
      <Text fontSize="xl" fontWeight="700" color="text.primary" mb={2}>Novo Relatório OPME</Text>
      <Text fontSize="sm" color="text.muted" mb={8}>
        Preencha as informações para gerar uma justificativa técnica com inteligência artificial.
      </Text>

      <StepperProgress activeStep={activeStep} onStepClick={setActiveStep} />

      {activeStep === 0 && (
        <StepDiagnostico
          cid={cid}
          onCidChange={handleCidChange}
          especialidade={especialidade}
          onEspecialidadeChange={setEspecialidade}
          diagnostico={diagnostico}
          onDiagnosticoChange={setDiagnostico}
          surgeryDescription={surgeryDescription}
          onSurgeryDescriptionChange={setSurgeryDescription}
          evidencesPreview={evidencesPreview}
          evidencesLoading={evidencesLoading}
          onNext={handleNext}
        />
      )}

      {activeStep === 1 && (
        <StepPaciente
          pacienteNome={pacienteNome}
          onPacienteNomeChange={setPacienteNome}
          healthPlan={healthPlan}
          onHealthPlanChange={setHealthPlan}
          searchQuery={searchQuery}
          onSearchQueryChange={handleProductSearchChange}
          loadingProducts={loadingProducts}
          products={products}
          selectedProduct={selectedProduct}
          onSelectProduct={handleSelectProduct}
          onClearProduct={() => setSelectedProduct(null)}
          showQuickRegister={showQuickRegister}
          onShowQuickRegister={(show) => {
            setShowQuickRegister(show);
            if (show) setQuickName(searchQuery);
          }}
          quickName={quickName}
          onQuickNameChange={setQuickName}
          quickAnvisa={quickAnvisa}
          onQuickAnvisaChange={setQuickAnvisa}
          quickFabricante={quickFabricante}
          onQuickFabricanteChange={setQuickFabricante}
          quickTuss={quickTuss}
          onQuickTussChange={setQuickTuss}
          savingProduct={savingProduct}
          onQuickRegister={handleQuickRegister}
          onBack={handleBack}
          onNext={handleNext}
        />
      )}

      {activeStep === 2 && (
        <StepGeracaoIA
          pipelineLoading={pipelineLoading}
          pipelineMessages={pipelineMessages}
          pipelineStep={pipelineStep}
          textRevealing={textRevealing}
          pipelineResult={pipelineResult}
          questions={questions}
          questionAnswers={questionAnswers}
          onQuestionAnswerChange={(secao, val) => setQuestionAnswers((prev) => ({ ...prev, [secao]: val }))}
          onSubmitAnswers={submitAnswers}
          justificativa={justificativa}
          onJustificativaChange={handleJustificativaChange}
          onTextRevealComplete={() => {
            setTextRevealing(false);
            setJustificativa(pipelineResult?.justificativa || '');
          }}
          checklist={checklist}
          approved={approved}
          auditSummary={auditSummary}
          onRegenerate={handleRegenerate}
          onNext={handleStepGeracaoNext}
        />
      )}

      {activeStep === 3 && (
        <StepRevisao
          approved={approved}
          pacienteNome={pacienteNome}
          cid={cid}
          selectedProduct={selectedProduct}
          healthPlan={healthPlan}
          justificativa={justificativa}
          onBack={() => setActiveStep(2)}
          onGoToReview={goToReview}
        />
      )}
    </Box>
  );
}
