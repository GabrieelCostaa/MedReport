import { Box, HStack, VStack, Text, Badge, Spinner, useColorModeValue } from '@chakra-ui/react';
import type { EvidencesPreview } from '../types';

interface EvidencesBadgeProps {
  preview: EvidencesPreview | null;
  loading: boolean;
}

export default function EvidencesBadge({ preview, loading }: EvidencesBadgeProps) {
  const loadingBg = useColorModeValue('yellow.50', 'yellow.900');
  const loadingBorder = useColorModeValue('yellow.200', 'yellow.700');
  const loadingText = useColorModeValue('yellow.700', 'yellow.200');
  const successBg = useColorModeValue('green.50', 'green.900');
  const successBorder = useColorModeValue('green.200', 'green.700');

  if (loading) {
    return (
      <HStack mt={2} p={2} bg={loadingBg} borderRadius="md" border="1px solid" borderColor={loadingBorder}>
        <Spinner size="sm" color="yellow.500" />
        <Text fontSize="sm" color={loadingText}>Buscando referências no PubMed...</Text>
      </HStack>
    );
  }
  if (!preview) return null;
  if (preview.total_count === 0) {
    return (
      <Box mt={2} p={2} bg="surface.subtle" borderRadius="md" border="1px solid" borderColor="border.muted">
        <Text fontSize="sm" color="text.muted">Nenhuma evidência encontrada para este CID</Text>
      </Box>
    );
  }
  return (
    <Box mt={2} p={3} bg={successBg} borderRadius="md" border="1px solid" borderColor={successBorder}>
      <HStack mb={2}>
        <Badge colorScheme="brand" fontSize="sm" px={2} py={1}>
          {preview.total_count} evidências encontradas
        </Badge>
        <Text fontSize="xs" color="text.secondary">
          ({preview.internal_count} verificadas + {preview.pubmed_count} PubMed)
        </Text>
      </HStack>
      {preview.preview.length > 0 && (
        <VStack align="stretch" gap={1}>
          {preview.preview.map((ev, i) => (
            <Text key={i} fontSize="xs" color="text.secondary">
              {ev.autor} ({ev.ano}) — <Badge fontSize="2xs" colorScheme="blue">{ev.tipo}</Badge> — {ev.titulo_curto}
            </Text>
          ))}
        </VStack>
      )}
    </Box>
  );
}
