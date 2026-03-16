import { Box, HStack, VStack, Text, Badge } from '@chakra-ui/react';
import type { PipelineResult } from '../types';

interface ComplianceScoreProps {
  result: PipelineResult | null;
}

export default function ComplianceScoreBox({ result }: ComplianceScoreProps) {
  if (!result || result.approval_score === undefined) return null;

  const score = result.approval_score;
  const nivel = result.approval_nivel || 'desconhecido';
  const componentes = result.approval_componentes || {};
  const explicacao = result.approval_explicacao || [];
  const alertas = result.approval_alertas || [];
  const gaps = result.approval_gaps || [];
  const mode = result.compliance_mode || '';
  const suggestions = result.dut_suggestions || [];

  const nivelColor: Record<string, string> = {
    alto: 'green', medio: 'yellow', baixo: 'orange', critico: 'red',
  };
  const nivelLabel: Record<string, string> = {
    alto: 'Alta', medio: 'Média', baixo: 'Baixa', critico: 'Crítica',
  };
  const modeLabel: Record<string, string> = {
    rol_dut: 'Rol/DUT', fora_do_rol: 'Fora do Rol', cobertura_direta: 'Cobertura Direta',
  };

  const scoreColor = nivel === 'alto' ? 'green.500' : nivel === 'medio' ? 'yellow.500' : nivel === 'baixo' ? 'orange.500' : 'red.500';

  return (
    <Box mt={4} p={4} borderRadius="md" border="2px solid" borderColor={scoreColor} bg="surface">
      <HStack justify="space-between" mb={3}>
        <HStack>
          <Text fontWeight="bold" fontSize="sm">Completude Documental Estimada</Text>
          {mode && <Badge colorScheme="blue" fontSize="2xs">{modeLabel[mode] || mode}</Badge>}
        </HStack>
        <HStack>
          <Text fontSize="2xl" fontWeight="bold" color={scoreColor}>{score.toFixed(0)}</Text>
          <Text fontSize="sm" color="text.muted">/100</Text>
          <Badge colorScheme={nivelColor[nivel] || 'gray'} fontSize="xs">{nivelLabel[nivel] || nivel}</Badge>
        </HStack>
      </HStack>

      <HStack gap={4} mb={3} flexWrap="wrap">
        {Object.entries(componentes).map(([key, val]) => {
          if (key === 'anvisa_status') return null;
          const labels: Record<string, string> = {
            aderencia_dut: 'DUT', completude_tiss_tuss: 'TISS/TUSS',
            qualidade_justificativa: 'Justificativa', robustez_evidencia: 'Evidência',
          };
          return (
            <Box key={key} textAlign="center" flex="1" minW="70px">
              <Text fontSize="2xs" color="text.muted">{labels[key] || key}</Text>
              <Text fontSize="sm" fontWeight="bold">{typeof val === 'number' ? val.toFixed(0) : val}</Text>
            </Box>
          );
        })}
      </HStack>

      {explicacao.length > 0 && (
        <VStack align="stretch" gap={0} mb={2}>
          {explicacao.map((e, i) => (
            <Text key={i} fontSize="xs" color="text.secondary">{e}</Text>
          ))}
        </VStack>
      )}

      {alertas.length > 0 && (
        <Box p={2} bg="red.50" borderRadius="md" mb={2}>
          {alertas.map((a, i) => (
            <Text key={i} fontSize="xs" color="red.700" fontWeight="semibold">{a}</Text>
          ))}
        </Box>
      )}

      {gaps.length > 0 && (
        <Box p={2} bg="yellow.50" borderRadius="md" mb={2}>
          <Text fontSize="2xs" fontWeight="bold" color="yellow.800" mb={1}>Pontos a melhorar:</Text>
          {gaps.map((g, i) => (
            <Text key={i} fontSize="xs" color="yellow.700">{g}</Text>
          ))}
        </Box>
      )}

      {suggestions.length > 0 && (
        <Box p={2} bg="blue.50" borderRadius="md">
          <Text fontSize="2xs" fontWeight="bold" color="blue.800" mb={1}>Sugestões para o médico:</Text>
          {suggestions.map((s, i) => (
            <Text key={i} fontSize="xs" color="blue.700">{s}</Text>
          ))}
        </Box>
      )}
    </Box>
  );
}
