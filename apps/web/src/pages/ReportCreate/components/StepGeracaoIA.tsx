import {
  VStack,
  HStack,
  Box,
  Heading,
  Text,
  Button,
  Textarea,
  Alert,
  AlertIcon,
  Divider,
  Radio,
  RadioGroup,
  Stack,
  Flex,
} from '@chakra-ui/react';
import { fadeInUp } from '../animations';
import PipelineProgress from './PipelineProgress';
import TextReveal from './TextReveal';
import AuditLogHumanized from './AuditLog';
import HardValidationBox from './HardValidation';
import ComplianceScoreBox from './ComplianceScore';
import UsageBox from './UsageBox';
import type { PipelineResult, PipelineQuestion, ChecklistItem, ReferenceItem } from '../types';

interface StepGeracaoIAProps {
  pipelineLoading: boolean;
  pipelineMessages: string[];
  pipelineStep: string;
  textRevealing: boolean;
  pipelineResult: PipelineResult | null;
  questions: PipelineQuestion[];
  questionAnswers: Record<string, string>;
  onQuestionAnswerChange: (secao: string, value: string) => void;
  onSubmitAnswers: () => void;
  justificativa: string;
  onJustificativaChange: (text: string) => void;
  onTextRevealComplete: () => void;
  checklist: Record<string, boolean | ChecklistItem>;
  approved: boolean;
  auditSummary: Record<string, unknown> | null;
  onRegenerate: () => void;
  onNext: () => void;
}

export default function StepGeracaoIA({
  pipelineLoading,
  pipelineMessages,
  pipelineStep,
  textRevealing,
  pipelineResult,
  questions,
  questionAnswers,
  onQuestionAnswerChange,
  onSubmitAnswers,
  justificativa,
  onJustificativaChange,
  onTextRevealComplete,
  checklist,
  approved,
  auditSummary,
  onRegenerate,
  onNext,
}: StepGeracaoIAProps) {
  return (
    <Flex justify="center" w="100%">
      <VStack gap={4} align="stretch" w="100%" maxW="3xl">
        {/* Phase 1: Pipeline progress */}
        {pipelineLoading && (
          <PipelineProgress messages={pipelineMessages} currentStage={pipelineStep || 'researching'} />
        )}

        {/* Phase 2: Text being written live */}
        {!pipelineLoading && textRevealing && pipelineResult?.justificativa && (
          <TextReveal
            text={pipelineResult.justificativa}
            onComplete={onTextRevealComplete}
          />
        )}

        {/* Questions A/B/C */}
        {!pipelineLoading && !textRevealing && questions.length > 0 && !justificativa && (
          <Box mx="auto" w="100%" maxW="2xl">
            <Alert status="info" mb={4} borderRadius="lg">
              <AlertIcon />
              O assistente precisa de mais informações para gerar uma justificativa completa.
            </Alert>

            {questions.map((q, idx) => (
              <Box key={idx} p={4} bg="surface.subtle" borderRadius="lg" mb={4} border="1px solid" borderColor="border.subtle">
                <Text fontWeight="600" mb={3} fontSize="sm">{q.pergunta}</Text>
                <RadioGroup
                  value={questionAnswers[q.secao] || ''}
                  onChange={(val) => onQuestionAnswerChange(q.secao, val)}
                >
                  <Stack>
                    {q.opcoes.map((opt) => (
                      <Radio key={opt.id} value={opt.texto} colorScheme="blue">
                        <Text fontSize="sm"><strong>({opt.id})</strong> {opt.texto}</Text>
                      </Radio>
                    ))}
                  </Stack>
                </RadioGroup>
              </Box>
            ))}

            <Button
              colorScheme="brand"
              onClick={onSubmitAnswers}
              isDisabled={Object.keys(questionAnswers).length < questions.length}
              w="100%"
            >
              Enviar Respostas e Gerar
            </Button>
          </Box>
        )}

        {/* Phase 3: Editable result */}
        {!pipelineLoading && !textRevealing && justificativa && (
          <Box sx={{ animation: `${fadeInUp} 0.4s ease both` }}>
            {/* Justificativa editor */}
            <Box mb={6}>
              <HStack mb={3} justify="space-between">
                <Heading size="sm" color="text.secondary">Justificativa Técnica</Heading>
                <Text fontSize="2xs" color="text.subtle" textTransform="uppercase" letterSpacing="wider">
                  Editável
                </Text>
              </HStack>
              <Textarea
                value={justificativa}
                onChange={(e) => onJustificativaChange(e.target.value)}
                rows={16}
                fontSize="sm"
                lineHeight="1.8"
                borderColor="border.muted"
                borderRadius="lg"
                _focus={{ borderColor: 'brand.400', boxShadow: '0 0 0 1px var(--chakra-colors-brand-400)' }}
              />
            </Box>

            {/* References */}
            {pipelineResult?.referencias && pipelineResult.referencias.length > 0 && (
              <Box p={4} bg="surface.subtle" borderRadius="lg" border="1px solid" borderColor="border.subtle" mb={4}>
                <Heading size="xs" mb={3} color="text.secondary">Referências Bibliográficas</Heading>
                <VStack align="stretch" gap={1}>
                  {pipelineResult.referencias.map((ref, i) => {
                    const isRich = typeof ref === 'object' && ref !== null;
                    const texto = isRich ? (ref as ReferenceItem).texto : (ref as string);
                    const link = isRich ? (ref as ReferenceItem).link : undefined;
                    const doi = isRich ? (ref as ReferenceItem).doi : undefined;
                    return (
                      <HStack key={i} align="start" gap={2}>
                        <Text fontSize="xs" color="text.muted" fontFamily="mono" flexShrink={0} mt="1px">
                          {String(i + 1).padStart(2, '0')}
                        </Text>
                        <Text fontSize="xs" color="text.secondary" flex={1} lineHeight="tall">
                          {texto}
                          {doi && <Text as="span" color="text.subtle" fontSize="2xs"> DOI: {doi}</Text>}
                        </Text>
                        {link && (
                          <Button as="a" href={link} target="_blank" rel="noopener" size="xs" variant="ghost"
                            colorScheme="blue" fontSize="2xs" minW="auto" h="auto" p={1} flexShrink={0}>
                            Abrir
                          </Button>
                        )}
                      </HStack>
                    );
                  })}
                </VStack>
              </Box>
            )}

            {/* Audit log */}
            {pipelineResult?.audit_log && pipelineResult.audit_log.length > 0 && (
              <AuditLogHumanized entries={pipelineResult.audit_log} />
            )}

            <Divider my={5} borderColor="border.subtle" />

            {/* Checklist */}
            <Box mb={4}>
              <Heading size="xs" mb={3} color="text.secondary">Checklist de Conformidade</Heading>
              <VStack align="stretch" gap={2}>
                {Object.entries(checklist).map(([key, value], idx) => {
                  const isOk = typeof value === 'boolean' ? value : (value as ChecklistItem)?.ok;
                  const label = typeof value === 'object' && value !== null && 'label' in value
                    ? (value as ChecklistItem).label
                    : key.replace(/_/g, ' ');
                  return (
                    <HStack
                      key={key} py={2} px={3}
                      bg={isOk ? 'green.50' : 'red.50'}
                      borderRadius="md" border="1px solid"
                      borderColor={isOk ? 'green.100' : 'red.100'}
                      sx={{ animation: `${fadeInUp} 0.3s ease ${idx * 0.1}s both` }}
                    >
                      <Flex
                        w="20px" h="20px" borderRadius="full" align="center" justify="center"
                        bg={isOk ? 'green.500' : 'red.500'} color="white" flexShrink={0}
                      >
                        {isOk ? (
                          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                            <path d="M1.5 5L4 7.5L8.5 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                          </svg>
                        ) : (
                          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                            <path d="M2.5 2.5L7.5 7.5M7.5 2.5L2.5 7.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                          </svg>
                        )}
                      </Flex>
                      <Text fontSize="sm" color={isOk ? 'text.secondary' : 'red.700'} fontWeight={isOk ? '400' : '500'}>
                        {label}
                      </Text>
                    </HStack>
                  );
                })}
              </VStack>
            </Box>

            <HardValidationBox auditSummary={auditSummary} />
            <ComplianceScoreBox result={pipelineResult} />
            <UsageBox usage={pipelineResult?.usage} />

            {!approved && (
              <Alert status="warning" mt={4} borderRadius="lg">
                <AlertIcon />
                <Text fontSize="sm">O checklist não está completo. Revise a justificativa ou regenere.</Text>
              </Alert>
            )}

            <HStack mt={6} justify="flex-end" gap={3}>
              <Button
                variant="outline" onClick={onRegenerate} isLoading={pipelineLoading}
                borderColor="gray.300" color="text.secondary" borderRadius="lg"
                transition="all 0.3s cubic-bezier(0.65, 0.05, 0, 1)"
                _hover={{ bg: 'surface.subtle' }}
              >
                Regenerar
              </Button>
              <Button
                colorScheme="brand" onClick={onNext} px={8} borderRadius="lg"
                transition="all 0.3s cubic-bezier(0.65, 0.05, 0, 1)"
                _hover={{ transform: 'translateY(-2px)', shadow: 'lg' }}
              >
                Revisão e Download
              </Button>
            </HStack>
          </Box>
        )}
      </VStack>
    </Flex>
  );
}
