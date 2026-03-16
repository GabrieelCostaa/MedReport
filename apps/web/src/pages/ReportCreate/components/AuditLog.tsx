import { Box, HStack, VStack, Text, Badge } from '@chakra-ui/react';
import { fadeInUp } from '../animations';
import type { AuditLogEntry } from '../types';

interface AuditLogProps {
  entries: AuditLogEntry[];
}

export default function AuditLogHumanized({ entries }: AuditLogProps) {
  if (!entries || entries.length === 0) return null;

  const humanize = (entry: AuditLogEntry): { color: string; message: string; badge: string } => {
    const campo = entry.campo.replace(/_/g, ' ');
    if (entry.tipo === 'correcao' || entry.tipo === 'hard_validation') {
      return {
        color: 'orange',
        message: entry.original && entry.corrigido
          ? `Corrigimos ${campo} de "${entry.original}" para "${entry.corrigido}" para evitar glosa`
          : entry.motivo,
        badge: 'Correção',
      };
    }
    return {
      color: 'green',
      message: entry.motivo || `${campo} verificado`,
      badge: 'OK',
    };
  };

  return (
    <Box mt={4} p={4} bg="orange.50" borderRadius="lg" border="1px solid" borderColor="orange.200">
      <HStack mb={3} gap={2}>
        {/* Shield icon — SVG instead of emoji */}
        <Box color="orange.600" flexShrink={0}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 0L14.5 3v4.5c0 3.5-2.8 6.8-6.5 7.5C4.3 14.3 1.5 11 1.5 7.5V3L8 0zm0 1.5L2.5 4v3.5c0 2.9 2.3 5.6 5.5 6.2 3.2-.6 5.5-3.3 5.5-6.2V4L8 1.5z"/>
          </svg>
        </Box>
        <Text fontWeight="600" fontSize="sm" color="orange.800">
          Proteções Aplicadas
        </Text>
        <Badge colorScheme="orange" fontSize="2xs" variant="subtle">
          {entries.length}
        </Badge>
      </HStack>
      <VStack align="stretch" gap={2}>
        {entries.map((entry, i) => {
          const h = humanize(entry);
          return (
            <Box key={i} p={3} bg="surface" borderRadius="md" border="1px solid" borderColor="orange.100"
              sx={{ animation: `${fadeInUp} 0.3s ease ${i * 0.1}s both` }}>
              <HStack justify="space-between" mb={1}>
                <Badge colorScheme={h.color} fontSize="2xs" variant="subtle">{h.badge}</Badge>
                <Text fontSize="2xs" color="text.subtle" fontFamily="mono">{entry.campo}</Text>
              </HStack>
              <Text fontSize="xs" color="text.secondary">{h.message}</Text>
              {entry.original && entry.corrigido && entry.tipo !== 'hard_validation' && (
                <HStack mt={2} gap={2} fontSize="2xs">
                  <Text color="red.500" textDecoration="line-through" bg="red.50" px={1} borderRadius="sm">{entry.original}</Text>
                  <Box color="text.subtle">
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                      <path d="M2 6h6M6 3l3 3-3 3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </Box>
                  <Text color="green.600" fontWeight="600" bg="green.50" px={1} borderRadius="sm">{entry.corrigido}</Text>
                </HStack>
              )}
            </Box>
          );
        })}
      </VStack>
    </Box>
  );
}
