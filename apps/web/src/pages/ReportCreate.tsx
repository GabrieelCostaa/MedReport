import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Input,
  Textarea,
  VStack,
  HStack,
  Heading,
  Text,
  useToast,
  Stepper,
  Step,
  StepIndicator,
  StepStatus,
  StepTitle,
  StepDescription,
  StepSeparator,
  StepIcon,
  StepNumber,
  Badge,
  Spinner,
  Radio,
  RadioGroup,
  Stack,
  Alert,
  AlertIcon,
  Divider,
  useSteps,
  Select,
} from '@chakra-ui/react';
import { productsApi, type Product } from '../api/products';
import { aiAssistantApi, type PipelineResult, type PipelineQuestion, type ChecklistItem, type PipelineUsage } from '../api/ai-assistant';
import { evidencesApi, type EvidencesPreview } from '../api/evidences';

const STEPS = [
  { title: 'CID & Diagnóstico', description: 'Busca automática de evidências' },
  { title: 'Paciente & Material', description: 'Dados e seleção do produto' },
  { title: 'IA & Edição', description: 'Justificativa técnica' },
  { title: 'Revisão & PDF', description: 'Checklist e download' },
];

function HardValidationBox({ auditSummary }: { auditSummary: Record<string, unknown> | null }) {
  if (!auditSummary || !auditSummary.hard_validation) return null;
  const hv = auditSummary.hard_validation as { passed?: boolean; entities_found?: number; issues_count?: number };
  return (
    <Box mt={3} p={3} bg={hv.passed ? 'green.50' : 'red.50'} borderRadius="md">
      <Text fontWeight="bold" fontSize="sm" mb={1}>
        Validação Hard-Coded {hv.passed ? '(OK)' : '(BLOQUEADO)'}
      </Text>
      <Text fontSize="xs" color="gray.600">
        Entidades técnicas encontradas: {hv.entities_found || 0}
        {' | '}Issues: {hv.issues_count || 0}
      </Text>
    </Box>
  );
}

function EvidencesBadge({ preview, loading }: { preview: EvidencesPreview | null; loading: boolean }) {
  if (loading) {
    return (
      <HStack mt={2} p={2} bg="yellow.50" borderRadius="md" border="1px solid" borderColor="yellow.200">
        <Spinner size="sm" color="yellow.500" />
        <Text fontSize="sm" color="yellow.700">Buscando referências no PubMed...</Text>
      </HStack>
    );
  }
  if (!preview) return null;
  if (preview.total_count === 0) {
    return (
      <Box mt={2} p={2} bg="gray.50" borderRadius="md" border="1px solid" borderColor="gray.200">
        <Text fontSize="sm" color="gray.500">Nenhuma evidência encontrada para este CID</Text>
      </Box>
    );
  }
  return (
    <Box mt={2} p={3} bg="green.50" borderRadius="md" border="1px solid" borderColor="green.200">
      <HStack mb={2}>
        <Badge colorScheme="green" fontSize="sm" px={2} py={1}>
          {preview.total_count} evidências encontradas
        </Badge>
        <Text fontSize="xs" color="gray.600">
          ({preview.internal_count} verificadas + {preview.pubmed_count} PubMed)
        </Text>
      </HStack>
      {preview.preview.length > 0 && (
        <VStack align="stretch" gap={1}>
          {preview.preview.map((ev, i) => (
            <Text key={i} fontSize="xs" color="gray.600">
              {ev.autor} ({ev.ano}) — <Badge fontSize="2xs" colorScheme="blue">{ev.tipo}</Badge> — {ev.titulo_curto}
            </Text>
          ))}
        </VStack>
      )}
    </Box>
  );
}

function UsageBox({ usage }: { usage: PipelineUsage | null | undefined }) {
  if (!usage || !usage.totals) return null;
  const { totals, agents } = usage;
  return (
    <Box mt={3} p={3} bg="purple.50" borderRadius="md" border="1px solid" borderColor="purple.200">
      <Text fontWeight="bold" fontSize="sm" mb={2} color="purple.700">
        Custo da Geração
      </Text>
      <HStack gap={6} mb={2}>
        <Box>
          <Text fontSize="xs" color="gray.500">Total tokens</Text>
          <Text fontSize="sm" fontWeight="bold">{totals.total_tokens.toLocaleString()}</Text>
        </Box>
        <Box>
          <Text fontSize="xs" color="gray.500">Custo USD</Text>
          <Text fontSize="sm" fontWeight="bold" color="green.700">${totals.cost_usd.toFixed(4)}</Text>
        </Box>
        <Box>
          <Text fontSize="xs" color="gray.500">Custo BRL</Text>
          <Text fontSize="sm" fontWeight="bold" color="green.700">R$ {totals.cost_brl.toFixed(4)}</Text>
        </Box>
      </HStack>
      <Divider my={2} />
      {agents.map((a, i) => (
        <HStack key={i} justify="space-between" fontSize="xs" color="gray.600">
          <Text>{a.agent}</Text>
          <Text>{a.prompt_tokens.toLocaleString()} in + {a.completion_tokens.toLocaleString()} out = {a.total_tokens.toLocaleString()} tokens (${a.cost_usd.toFixed(4)})</Text>
        </HStack>
      ))}
    </Box>
  );
}

export default function ReportCreate() {
  const { activeStep, setActiveStep } = useSteps({ index: 0, count: STEPS.length });
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

  // Step 3: IA
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineResult, setPipelineResult] = useState<PipelineResult | null>(null);
  const [questions, setQuestions] = useState<PipelineQuestion[]>([]);
  const [questionAnswers, setQuestionAnswers] = useState<Record<string, string>>({});
  const [justificativa, setJustificativa] = useState('');
  const [sessionId, setSessionId] = useState('');

  // Step 4: Checklist (reativo)
  const [checklist, setChecklist] = useState<Record<string, boolean | ChecklistItem>>({});
  const [approved, setApproved] = useState(false);
  const [auditSummary, setAuditSummary] = useState<Record<string, unknown> | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  useEffect(() => {
    searchProducts('');
  }, [searchProducts]);

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
        toast({ title: 'Selecione um material OPME', status: 'warning' });
        return;
      }
      startPipeline();
      return;
    }
    setActiveStep(activeStep + 1);
  };

  const handleBack = () => setActiveStep(Math.max(0, activeStep - 1));

  const startPipeline = async () => {
    if (!selectedProduct) return;
    setPipelineLoading(true);
    setActiveStep(2);
    try {
      const result = await aiAssistantApi.startReport({
        product_id: selectedProduct.id,
        paciente_nome: pacienteNome,
        cid,
        diagnostico,
        surgery_description: surgeryDescription,
        health_plan: healthPlan,
        especialidade,
      });
      handlePipelineResult(result);
    } catch (e) {
      toast({ title: 'Erro ao iniciar assistente', status: 'error' });
    } finally {
      setPipelineLoading(false);
    }
  };

  const handlePipelineResult = (result: PipelineResult) => {
    setPipelineResult(result);
    setSessionId(result.session_id);
    if (result.step === 'questions' && result.questions) {
      setQuestions(result.questions);
    } else if (result.step === 'done') {
      setJustificativa(result.justificativa || '');
      setChecklist(result.checklist || {});
      setApproved(result.aprovado || false);
      if ((result as unknown as Record<string, unknown>).audit_summary) {
        setAuditSummary((result as unknown as Record<string, unknown>).audit_summary as Record<string, unknown>);
      }
    }
  };

  const runQuickCheck = useCallback(async (text: string) => {
    try {
      const res = await aiAssistantApi.quickCheck({
        justificativa_ia: text,
        diagnostico,
        falha_terapeutica: pipelineResult?.falha_terapeutica || '',
        risco_nao_realizacao: pipelineResult?.risco_nao_realizacao || '',
        base_legal_ans: pipelineResult?.base_legal || '',
        referencias_bib: pipelineResult?.referencias || [],
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
    try {
      const result = await aiAssistantApi.answer(sessionId, questionAnswers);
      handlePipelineResult(result);
    } catch {
      toast({ title: 'Erro ao enviar respostas', status: 'error' });
    } finally {
      setPipelineLoading(false);
    }
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
      navigate(`/reports/${pipelineResult.report_id}/review`);
    } else {
      toast({ title: 'Relatório ainda não foi salvo', status: 'warning' });
    }
  };

  return (
    <Box>
      <Heading size="md" mb={6}>Novo Relatório OPME</Heading>

      <Stepper index={activeStep} mb={8} colorScheme="green">
        {STEPS.map((step, index) => (
          <Step key={index} onClick={() => index < activeStep && setActiveStep(index)}>
            <StepIndicator>
              <StepStatus
                complete={<StepIcon />}
                incomplete={<StepNumber />}
                active={<StepNumber />}
              />
            </StepIndicator>
            <Box flexShrink="0">
              <StepTitle>{step.title}</StepTitle>
              <StepDescription>{step.description}</StepDescription>
            </Box>
            <StepSeparator />
          </Step>
        ))}
      </Stepper>

      {/* Step 1: CID & Diagnóstico */}
      {activeStep === 0 && (
        <VStack gap={4} align="stretch" maxW="2xl">
          <HStack gap={4}>
            <FormControl isRequired flex={1}>
              <FormLabel>CID</FormLabel>
              <Input value={cid} onChange={(e) => handleCidChange(e.target.value)} placeholder="Ex: M17.9" />
            </FormControl>
            <FormControl flex={1}>
              <FormLabel>Especialidade</FormLabel>
              <Select value={especialidade} onChange={(e) => setEspecialidade(e.target.value)} placeholder="Selecione">
                <option value="Ortopedia">Ortopedia</option>
                <option value="Neurocirurgia">Neurocirurgia</option>
                <option value="Cardiologia">Cardiologia</option>
                <option value="Cirurgia Vascular">Cirurgia Vascular</option>
                <option value="Cirurgia Geral">Cirurgia Geral</option>
                <option value="Urologia">Urologia</option>
                <option value="Ginecologia">Ginecologia</option>
                <option value="Oftalmologia">Oftalmologia</option>
                <option value="Otorrinolaringologia">Otorrinolaringologia</option>
                <option value="Outra">Outra</option>
              </Select>
            </FormControl>
          </HStack>
          <EvidencesBadge preview={evidencesPreview} loading={evidencesLoading} />
          <FormControl isRequired>
            <FormLabel>Diagnóstico</FormLabel>
            <Textarea value={diagnostico} onChange={(e) => setDiagnostico(e.target.value)} placeholder="Descrição clínica do diagnóstico" rows={3} />
          </FormControl>
          <FormControl>
            <FormLabel>Procedimento cirúrgico</FormLabel>
            <Textarea value={surgeryDescription} onChange={(e) => setSurgeryDescription(e.target.value)} placeholder="Ex: Artroplastia total de joelho" rows={2} />
          </FormControl>
          <Button colorScheme="green" onClick={handleNext}>Próximo: Paciente & Material</Button>
        </VStack>
      )}

      {/* Step 2: Paciente + Material + Convênio */}
      {activeStep === 1 && (
        <VStack gap={4} align="stretch" maxW="2xl">
          <FormControl isRequired>
            <FormLabel>Nome do Paciente</FormLabel>
            <Input value={pacienteNome} onChange={(e) => setPacienteNome(e.target.value)} placeholder="Nome completo" />
          </FormControl>
          <FormControl>
            <FormLabel>Convênio</FormLabel>
            <Input value={healthPlan} onChange={(e) => setHealthPlan(e.target.value)} placeholder="Nome do convênio" />
          </FormControl>
          <Divider />
          <FormControl>
            <FormLabel>Buscar material OPME</FormLabel>
            <HStack>
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Nome ou linha do produto"
                onKeyDown={(e) => e.key === 'Enter' && searchProducts(searchQuery)}
              />
              <Button onClick={() => searchProducts(searchQuery)} isLoading={loadingProducts} variant="outline">
                Buscar
              </Button>
            </HStack>
          </FormControl>

          {products.length === 0 && !loadingProducts && (
            <Text color="gray.500" fontSize="sm">Nenhum produto encontrado. Use o campo de busca.</Text>
          )}

          <VStack align="stretch" gap={2} maxH="400px" overflowY="auto">
            {products.map((p) => (
              <Box
                key={p.id}
                p={4}
                border="2px solid"
                borderColor={selectedProduct?.id === p.id ? 'green.400' : 'gray.200'}
                borderRadius="md"
                cursor="pointer"
                onClick={() => setSelectedProduct(p)}
                bg={selectedProduct?.id === p.id ? 'green.50' : 'white'}
                _hover={{ borderColor: 'green.300' }}
              >
                <HStack justify="space-between">
                  <Box>
                    <Text fontWeight="bold">{p.nome}</Text>
                    {p.linha && <Badge colorScheme="blue" fontSize="xs">{p.linha}</Badge>}
                  </Box>
                  {p.registro_anvisa && <Text fontSize="xs" color="gray.500">ANVISA: {p.registro_anvisa}</Text>}
                </HStack>
                {p.diferenciais_clinicos && (
                  <Text fontSize="sm" color="gray.600" mt={1} noOfLines={2}>{p.diferenciais_clinicos}</Text>
                )}
                {p.codigo_tuss_sugerido && (
                  <Text fontSize="xs" color="gray.400" mt={1}>TUSS: {p.codigo_tuss_sugerido}</Text>
                )}
              </Box>
            ))}
          </VStack>

          <HStack>
            <Button variant="outline" onClick={handleBack}>Voltar</Button>
            <Button colorScheme="green" onClick={handleNext} isDisabled={!selectedProduct}>
              Gerar Justificativa com IA
            </Button>
          </HStack>
        </VStack>
      )}

      {/* Step 3: IA & Edição */}
      {activeStep === 2 && (
        <VStack gap={4} align="stretch" maxW="3xl">
          {pipelineLoading && (
            <Box textAlign="center" py={12}>
              <Spinner size="xl" color="green.500" thickness="4px" />
              <Text mt={4} color="gray.600">O assistente está gerando a justificativa técnica...</Text>
              <Text fontSize="sm" color="gray.400" mt={2}>Pipeline: Pesquisador → Redator → Auditor</Text>
            </Box>
          )}

          {/* Perguntas A/B/C */}
          {!pipelineLoading && questions.length > 0 && !justificativa && (
            <Box>
              <Alert status="info" mb={4}>
                <AlertIcon />
                O assistente precisa de mais informações para gerar uma justificativa completa.
              </Alert>

              {questions.map((q, idx) => (
                <Box key={idx} p={4} bg="gray.50" borderRadius="md" mb={4}>
                  <Text fontWeight="bold" mb={3}>{q.pergunta}</Text>
                  <RadioGroup
                    value={questionAnswers[q.secao] || ''}
                    onChange={(val) => setQuestionAnswers((prev) => ({ ...prev, [q.secao]: val }))}
                  >
                    <Stack>
                      {q.opcoes.map((opt) => (
                        <Radio key={opt.id} value={opt.texto}>
                          <Text fontSize="sm"><strong>({opt.id})</strong> {opt.texto}</Text>
                        </Radio>
                      ))}
                    </Stack>
                  </RadioGroup>
                </Box>
              ))}

              <Button
                colorScheme="green"
                onClick={submitAnswers}
                isDisabled={Object.keys(questionAnswers).length < questions.length}
              >
                Enviar Respostas e Gerar
              </Button>
            </Box>
          )}

          {/* Resultado: Justificativa + Checklist */}
          {!pipelineLoading && justificativa && (
            <Box>
              <Heading size="sm" mb={3}>Justificativa Técnica (editável)</Heading>
              <Textarea
                value={justificativa}
                onChange={(e) => handleJustificativaChange(e.target.value)}
                rows={16}
                fontSize="sm"
              />

              {pipelineResult?.referencias && pipelineResult.referencias.length > 0 && (
                <Box mt={4} p={3} bg="blue.50" borderRadius="md">
                  <Text fontWeight="bold" fontSize="sm" mb={2}>Referências Bibliográficas</Text>
                  {pipelineResult.referencias.map((ref, i) => (
                    <Text key={i} fontSize="xs" color="gray.700">{i + 1}. {ref}</Text>
                  ))}
                </Box>
              )}

              {pipelineResult?.audit_log && pipelineResult.audit_log.length > 0 && (
                <Box mt={4} p={3} bg="orange.50" borderRadius="md">
                  <Text fontWeight="bold" fontSize="sm" mb={2}>Log de Auditoria (Agente C)</Text>
                  {pipelineResult.audit_log.map((entry, i) => (
                    <Text key={i} fontSize="xs" color="gray.700">
                      [{entry.tipo}] {entry.campo}: {entry.motivo}
                    </Text>
                  ))}
                </Box>
              )}

              <Divider my={4} />

              <Heading size="sm" mb={3}>Checklist de Saída (6 itens obrigatórios)</Heading>
              <VStack align="stretch" gap={1}>
                {Object.entries(checklist).map(([key, value]) => {
                  const isOk = typeof value === 'boolean' ? value : (value as ChecklistItem)?.ok;
                  const label = typeof value === 'object' && value !== null && 'label' in value
                    ? (value as ChecklistItem).label
                    : key.replace(/_/g, ' ');
                  return (
                    <HStack key={key}>
                      <Badge colorScheme={isOk ? 'green' : 'red'} fontSize="xs" minW="20px" textAlign="center">
                        {isOk ? '✓' : '✗'}
                      </Badge>
                      <Text fontSize="sm" color={isOk ? 'gray.700' : 'red.600'} fontWeight={isOk ? 'normal' : 'semibold'}>
                        {label}
                      </Text>
                    </HStack>
                  );
                })}
              </VStack>

              <HardValidationBox auditSummary={auditSummary} />
              <UsageBox usage={pipelineResult?.usage} />

              {!approved && (
                <Alert status="warning" mt={4}>
                  <AlertIcon />
                  O checklist não está completo. Revise a justificativa ou regenere.
                </Alert>
              )}

              <HStack mt={4}>
                <Button variant="outline" onClick={handleRegenerate} isLoading={pipelineLoading}>
                  Regenerar
                </Button>
                <Button colorScheme="green" onClick={() => setActiveStep(3)}>
                  Próximo: Revisão & PDF
                </Button>
              </HStack>
            </Box>
          )}
        </VStack>
      )}

      {/* Step 4: Revisão & PDF */}
      {activeStep === 3 && (
        <VStack gap={4} align="stretch" maxW="2xl">
          <Alert status={approved ? 'success' : 'warning'}>
            <AlertIcon />
            {approved
              ? 'Relatório aprovado pelo checklist. Pronto para download.'
              : 'Checklist incompleto. O relatório pode necessitar de ajustes.'}
          </Alert>

          <Box p={4} bg="gray.50" borderRadius="md">
            <Text fontSize="sm"><strong>Paciente:</strong> {pacienteNome}</Text>
            <Text fontSize="sm"><strong>CID:</strong> {cid}</Text>
            <Text fontSize="sm"><strong>Material:</strong> {selectedProduct?.nome}</Text>
            <Text fontSize="sm"><strong>Convênio:</strong> {healthPlan || 'Não informado'}</Text>
          </Box>

          <Box p={4} bg="white" border="1px solid" borderColor="gray.200" borderRadius="md">
            <Text fontSize="sm" whiteSpace="pre-wrap">{justificativa}</Text>
          </Box>

          <HStack>
            <Button variant="outline" onClick={() => setActiveStep(2)}>Voltar para Edição</Button>
            <Button colorScheme="green" onClick={goToReview}>
              Abrir Revisão & Download PDF
            </Button>
          </HStack>
        </VStack>
      )}
    </Box>
  );
}
