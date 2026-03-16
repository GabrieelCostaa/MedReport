import { Box, Text } from '@chakra-ui/react';

interface HardValidationBoxProps {
  auditSummary: Record<string, unknown> | null;
}

export default function HardValidationBox({ auditSummary }: HardValidationBoxProps) {
  if (!auditSummary || !auditSummary.hard_validation) return null;
  const hv = auditSummary.hard_validation as { passed?: boolean; entities_found?: number; issues_count?: number };
  return (
    <Box mt={3} p={3} bg={hv.passed ? 'green.50' : 'red.50'} borderRadius="md">
      <Text fontWeight="bold" fontSize="sm" mb={1}>
        Validação Hard-Coded {hv.passed ? '(OK)' : '(BLOQUEADO)'}
      </Text>
      <Text fontSize="xs" color="text.secondary">
        Entidades técnicas encontradas: {hv.entities_found || 0}
        {' | '}Issues: {hv.issues_count || 0}
      </Text>
    </Box>
  );
}
