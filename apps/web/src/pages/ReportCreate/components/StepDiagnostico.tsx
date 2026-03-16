import {
  VStack,
  HStack,
  Flex,
  Box,
  FormControl,
  FormLabel,
  Input,
  Textarea,
  Button,
  Select,
  Text,
  Icon,
} from '@chakra-ui/react';
import EvidencesBadge from './EvidencesBadge';
import type { EvidencesPreview } from '../types';

interface StepDiagnosticoProps {
  cid: string;
  onCidChange: (value: string) => void;
  especialidade: string;
  onEspecialidadeChange: (value: string) => void;
  diagnostico: string;
  onDiagnosticoChange: (value: string) => void;
  surgeryDescription: string;
  onSurgeryDescriptionChange: (value: string) => void;
  evidencesPreview: EvidencesPreview | null;
  evidencesLoading: boolean;
  onNext: () => void;
}

function StethoscopeIcon(props: React.ComponentProps<typeof Icon>) {
  return (
    <Icon viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M4.8 2.449a.5.5 0 0 0-.764.058l-1.036 1.43a.5.5 0 0 0 .058.764l2.571 1.857A5.5 5.5 0 0 0 7.5 13.5c0 .266-.019.528-.056.784A4.501 4.501 0 0 0 12 18.5a4.5 4.5 0 0 0 4.556-4.216A5.5 5.5 0 0 0 19 9.5V4" />
      <path d="M8 2.5l1.5 2M16 2.5L14.5 4.5" />
      <circle cx="19" cy="3" r="1" />
    </Icon>
  );
}

const fieldHoverStyle = {
  borderColor: 'gray.300',
  shadow: 'sm',
};

export default function StepDiagnostico({
  cid,
  onCidChange,
  especialidade,
  onEspecialidadeChange,
  diagnostico,
  onDiagnosticoChange,
  surgeryDescription,
  onSurgeryDescriptionChange,
  evidencesPreview,
  evidencesLoading,
  onNext,
}: StepDiagnosticoProps) {
  return (
    <Flex justify="center" w="full">
      <VStack gap={6} align="stretch" maxW="2xl" mx="auto" w="full">
        {/* Header card */}
        <HStack
          spacing={4}
          bg="brand.surface"
          p={5}
          borderRadius="xl"
          border="1px solid"
          borderColor="brand.border"
        >
          <Flex
            align="center"
            justify="center"
            w={12}
            h={12}
            borderRadius="lg"
            bg="brand.border"
            color="brand.text"
            flexShrink={0}
          >
            <StethoscopeIcon boxSize={6} />
          </Flex>
          <Box>
            <Text fontSize="lg" fontWeight="semibold" color="text.primary">
              Passo 1 — Diagnóstico
            </Text>
            <Text fontSize="sm" color="text.muted">
              Informe o CID, especialidade e descreva o diagnóstico clínico do paciente.
            </Text>
          </Box>
        </HStack>

        {/* Form card */}
        <Box
          bg="surface"
          p={6}
          borderRadius="xl"
          border="1px solid"
          borderColor="border.subtle"
          shadow="sm"
        >
          <VStack gap={5} align="stretch">
            <HStack gap={4}>
              <FormControl isRequired flex={1}>
                <FormLabel fontWeight="medium" fontSize="sm" color="text.secondary">
                  CID
                </FormLabel>
                <Input
                  value={cid}
                  onChange={(e) => onCidChange(e.target.value)}
                  placeholder="Ex: M17.9"
                  borderRadius="lg"
                  _hover={fieldHoverStyle}
                />
              </FormControl>
              <FormControl flex={1}>
                <FormLabel fontWeight="medium" fontSize="sm" color="text.secondary">
                  Especialidade
                </FormLabel>
                <Select
                  value={especialidade}
                  onChange={(e) => onEspecialidadeChange(e.target.value)}
                  placeholder="Selecione"
                  borderRadius="lg"
                  _hover={fieldHoverStyle}
                >
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
              <FormLabel fontWeight="medium" fontSize="sm" color="text.secondary">
                Diagnóstico
              </FormLabel>
              <Textarea
                value={diagnostico}
                onChange={(e) => onDiagnosticoChange(e.target.value)}
                placeholder="Descrição clínica do diagnóstico"
                rows={3}
                borderRadius="lg"
                _hover={fieldHoverStyle}
              />
            </FormControl>

            <FormControl>
              <FormLabel fontWeight="medium" fontSize="sm" color="text.secondary">
                Procedimento cirúrgico
              </FormLabel>
              <Textarea
                value={surgeryDescription}
                onChange={(e) => onSurgeryDescriptionChange(e.target.value)}
                placeholder="Ex: Artroplastia total de joelho"
                rows={2}
                borderRadius="lg"
                _hover={fieldHoverStyle}
              />
            </FormControl>

            <Button
              colorScheme="brand"
              onClick={onNext}
              size="lg"
              borderRadius="lg"
              mt={2}
              transition="all 0.3s cubic-bezier(0.65, 0.05, 0, 1)"
              _hover={{ transform: 'translateY(-2px)', shadow: 'lg' }}
            >
              Próximo: Paciente & Material
            </Button>
          </VStack>
        </Box>
      </VStack>
    </Flex>
  );
}
