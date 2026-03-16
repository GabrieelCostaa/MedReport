import { Box, HStack, Text, Divider } from '@chakra-ui/react';
import type { PipelineUsage } from '../types';

interface UsageBoxProps {
  usage: PipelineUsage | null | undefined;
}

export default function UsageBox({ usage }: UsageBoxProps) {
  if (!usage || !usage.totals) return null;
  const { totals, agents } = usage;
  return (
    <Box mt={3} p={3} bg="purple.50" borderRadius="md" border="1px solid" borderColor="purple.200">
      <Text fontWeight="bold" fontSize="sm" mb={2} color="purple.700">
        Custo da Geração
      </Text>
      <HStack gap={6} mb={2}>
        <Box>
          <Text fontSize="xs" color="text.muted">Total tokens</Text>
          <Text fontSize="sm" fontWeight="bold">{totals.total_tokens.toLocaleString()}</Text>
        </Box>
        <Box>
          <Text fontSize="xs" color="text.muted">Custo USD</Text>
          <Text fontSize="sm" fontWeight="bold" color="brand.700">${totals.cost_usd.toFixed(4)}</Text>
        </Box>
        <Box>
          <Text fontSize="xs" color="text.muted">Custo BRL</Text>
          <Text fontSize="sm" fontWeight="bold" color="brand.700">R$ {totals.cost_brl.toFixed(4)}</Text>
        </Box>
      </HStack>
      <Divider my={2} />
      {agents.map((a, i) => (
        <HStack key={i} justify="space-between" fontSize="xs" color="text.secondary">
          <Text>{a.agent}</Text>
          <Text>{a.prompt_tokens.toLocaleString()} in + {a.completion_tokens.toLocaleString()} out = {a.total_tokens.toLocaleString()} tokens (${a.cost_usd.toFixed(4)})</Text>
        </HStack>
      ))}
    </Box>
  );
}
