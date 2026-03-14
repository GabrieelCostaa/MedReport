import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Checkbox,
  Text,
  VStack,
  Heading,
  useToast,
  UnorderedList,
  ListItem,
  Divider,
} from '@chakra-ui/react';
import { authApi } from '../api/auth';

const LEGAL_BASIS_TEXT = `
Esta plataforma trata dados pessoais, incluindo dados de saúde (dados sensíveis), 
com fundamento nas seguintes bases legais previstas na Lei 13.709/2018 (LGPD):
`;

const LEGAL_BASES = [
  {
    title: 'CONSENTIMENTO (Art. 11, I)',
    description: 'Para funcionalidades opcionais, comunicações e preferências personalizadas.',
  },
  {
    title: 'CUMPRIMENTO DE OBRIGAÇÃO LEGAL/REGULATÓRIA (Art. 11, II, "a")',
    description:
      'Geração de guias TISS conforme exigido pela ANS (RN 501/2022). O padrão TISS é obrigatório para troca de informações na saúde suplementar.',
  },
  {
    title: 'TUTELA DA SAÚDE (Art. 11, II, "f")',
    description:
      'Processamento necessário para procedimentos de saúde, em procedimento realizado por profissionais de saúde, serviços de saúde ou autoridade sanitária.',
  },
];

const USER_RIGHTS = [
  'Acesso aos seus dados pessoais (Art. 18, II)',
  'Correção de dados incompletos, inexatos ou desatualizados (Art. 18, III)',
  'Anonimização, bloqueio ou eliminação de dados desnecessários (Art. 18, IV)',
  'Portabilidade dos dados (Art. 18, V)',
  'Revogação do consentimento, quando aplicável (Art. 18, IX)',
  'Informação sobre compartilhamento com terceiros (Art. 18, VII)',
];

export default function LegalBasis() {
  const [acknowledged, setAcknowledged] = useState(false);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();

  const handleAcknowledge = async () => {
    if (!acknowledged) {
      toast({ title: 'Marque a opção de ciência', status: 'warning' });
      return;
    }
    setLoading(true);
    try {
      await authApi.acknowledgeLegalBasis();
      toast({ title: 'Ciência registrada com sucesso', status: 'success' });
      navigate('/dashboard/reports');
    } catch {
      toast({ title: 'Erro ao registrar ciência', status: 'error' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box maxW="3xl" mx="auto" mt={10} p={8} bg="white" borderRadius="lg" shadow="md">
      <Heading size="lg" mb={4} color="brand.600">
        Bases Legais para Tratamento de Dados (LGPD)
      </Heading>

      <Text mb={4} fontSize="sm" color="gray.700">
        {LEGAL_BASIS_TEXT}
      </Text>

      <VStack align="stretch" gap={4} mb={6}>
        {LEGAL_BASES.map((basis, idx) => (
          <Box key={idx} p={4} bg="gray.50" borderRadius="md">
            <Text fontWeight="bold" fontSize="sm" color="brand.700">
              {basis.title}
            </Text>
            <Text fontSize="sm" color="gray.600" mt={1}>
              {basis.description}
            </Text>
          </Box>
        ))}
      </VStack>

      <Divider my={4} />

      <Heading size="sm" mb={3}>
        Seus direitos (Art. 18 da LGPD)
      </Heading>
      <UnorderedList mb={6} fontSize="sm" color="gray.600" spacing={1}>
        {USER_RIGHTS.map((right, idx) => (
          <ListItem key={idx}>{right}</ListItem>
        ))}
      </UnorderedList>

      <Box p={4} bg="blue.50" borderRadius="md" mb={6}>
        <Text fontSize="xs" color="blue.800">
          <strong>Nota sobre penalidades regulatórias:</strong> O descumprimento das normas
          relativas ao padrão TISS pode acarretar multa de R$ 35.000,00 (Art. 47, RN 489/2022) e
          multa diária de R$ 5.000,00 (Art. 13, RN 489/2022) para operadoras e prestadores.
        </Text>
      </Box>

      <VStack align="stretch" gap={4}>
        <Checkbox
          isChecked={acknowledged}
          onChange={(e) => setAcknowledged(e.target.checked)}
          colorScheme="green"
        >
          <Text fontSize="sm">
            Declaro ciência das bases legais e finalidades do tratamento de dados conforme a LGPD.
          </Text>
        </Checkbox>
        <Button
          colorScheme="green"
          onClick={handleAcknowledge}
          isLoading={loading}
          isDisabled={!acknowledged}
        >
          Continuar
        </Button>
      </VStack>
    </Box>
  );
}
