import { useEffect, useState, useCallback } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import {
  Box,
  Button,
  Heading,
  Text,
  Badge,
  HStack,
  VStack,
  Input,
  InputGroup,
  InputLeftElement,
  Skeleton,
  IconButton,
} from '@chakra-ui/react';
import { reportsApi, type Report } from '../api/reports';

const PER_PAGE = 10;

export default function ReportList() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);

  const fetchPage = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const res = await reportsApi.list(p, PER_PAGE);
      setReports(res.items);
      setTotalPages(res.total_pages);
      setTotal(res.total);
      setPage(res.page);
    } catch {
      setReports([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPage(1);
  }, [fetchPage]);

  const filtered = search
    ? reports.filter(r => {
        const q = search.toLowerCase();
        return (
          r.id.toLowerCase().includes(q) ||
          (r.patient_diagnosis || '').toLowerCase().includes(q)
        );
      })
    : reports;

  const handlePrev = () => { if (page > 1) fetchPage(page - 1); };
  const handleNext = () => { if (page < totalPages) fetchPage(page + 1); };

  return (
    <Box>
      <HStack justify="space-between" mb={6} flexWrap="wrap" gap={3}>
        <Box>
          <Heading size="md" fontWeight="700" color="gray.800">
            Documentos
          </Heading>
          <Text fontSize="sm" color="gray.500" mt={1}>
            {total} relatorio{total !== 1 ? 's' : ''} gerado{total !== 1 ? 's' : ''}
          </Text>
        </Box>
        <Button
          as={RouterLink}
          to="/dashboard/reports/new"
          colorScheme="brand"
          size="sm"
          fontWeight="600"
          leftIcon={
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M12 5v14M5 12h14" />
            </svg>
          }
        >
          Novo Relatorio
        </Button>
      </HStack>

      {/* Search */}
      <InputGroup mb={4} maxW="400px">
        <InputLeftElement pointerEvents="none">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#a0aec0" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
        </InputLeftElement>
        <Input
          placeholder="Buscar por diagnostico..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          bg="white"
          borderRadius="lg"
          fontSize="sm"
        />
      </InputGroup>

      {loading ? (
        <VStack align="stretch" gap={2}>
          {[1, 2, 3, 4].map(i => (
            <Box key={i} p={4} bg="white" borderRadius="lg" border="1px solid" borderColor="gray.100">
              <HStack justify="space-between" align="start">
                <Box flex={1}>
                  <Skeleton h="14px" w="55%" mb={2} />
                  <HStack gap={3}>
                    <Skeleton h="10px" w="100px" />
                    <Skeleton h="10px" w="60px" />
                  </HStack>
                </Box>
                <Skeleton h="20px" w="70px" borderRadius="full" />
              </HStack>
            </Box>
          ))}
        </VStack>
      ) : filtered.length === 0 ? (
        <Box p={12} bg="white" borderRadius="xl" border="1px solid" borderColor="gray.100" textAlign="center">
          <Text fontSize="3xl" mb={3}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#cbd5e0" strokeWidth="1.5" style={{ margin: '0 auto' }}>
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
          </Text>
          <Text color="gray.500" fontWeight="500" mb={1}>Nenhum relatorio encontrado</Text>
          <Text color="gray.400" fontSize="sm" mb={4}>
            {search ? 'Tente outro termo de busca' : 'Crie seu primeiro relatorio com IA'}
          </Text>
          {!search && (
            <Button as={RouterLink} to="/dashboard/reports/new" colorScheme="brand" size="sm">
              Criar Relatorio
            </Button>
          )}
        </Box>
      ) : (
        <>
          <VStack align="stretch" gap={2}>
            {filtered.map((r) => (
              <Box
                key={r.id}
                as={RouterLink}
                to={`/dashboard/reports/${r.id}/review`}
                p={4}
                bg="white"
                borderRadius="lg"
                border="1px solid"
                borderColor="gray.100"
                _hover={{ borderColor: 'brand.200', shadow: 'sm' }}
                transition="all 0.15s"
                display="block"
                textDecoration="none"
              >
                <HStack justify="space-between" align="start">
                  <Box flex={1}>
                    <Text fontSize="sm" fontWeight="500" color="gray.800">
                      {r.patient_diagnosis || 'Relatorio #' + r.id.slice(0, 8)}
                    </Text>
                    <HStack mt={2} gap={3}>
                      <Text fontSize="xs" color="gray.400">
                        {new Date(r.created_at).toLocaleDateString('pt-BR', {
                          day: '2-digit', month: 'short', year: 'numeric',
                          hour: '2-digit', minute: '2-digit',
                        })}
                      </Text>
                      <Text fontSize="xs" color="gray.400">
                        ID: {r.id.slice(0, 8)}
                      </Text>
                    </HStack>
                  </Box>
                  <Badge
                    colorScheme={r.status === 'signed' ? 'green' : 'yellow'}
                    fontSize="xs"
                    borderRadius="full"
                    px={2}
                    py={0.5}
                  >
                    {r.status === 'signed' ? 'Assinado' : 'Rascunho'}
                  </Badge>
                </HStack>
              </Box>
            ))}
          </VStack>

          {/* Pagination */}
          {totalPages > 1 && (
            <HStack justify="center" mt={6} gap={2}>
              <IconButton
                aria-label="Pagina anterior"
                variant="outline"
                size="sm"
                borderRadius="lg"
                isDisabled={page <= 1}
                onClick={handlePrev}
                icon={
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="15 18 9 12 15 6" />
                  </svg>
                }
              />
              {Array.from({ length: totalPages }, (_, i) => i + 1)
                .filter(p => p === 1 || p === totalPages || Math.abs(p - page) <= 1)
                .reduce<(number | 'dots')[]>((acc, p, idx, arr) => {
                  if (idx > 0 && p - (arr[idx - 1] as number) > 1) acc.push('dots');
                  acc.push(p);
                  return acc;
                }, [])
                .map((item, idx) =>
                  item === 'dots' ? (
                    <Text key={`dots-${idx}`} fontSize="sm" color="gray.400" px={1}>...</Text>
                  ) : (
                    <Button
                      key={item}
                      size="sm"
                      variant={item === page ? 'solid' : 'ghost'}
                      colorScheme={item === page ? 'brand' : undefined}
                      borderRadius="lg"
                      minW="36px"
                      onClick={() => fetchPage(item as number)}
                    >
                      {item}
                    </Button>
                  )
                )}
              <IconButton
                aria-label="Proxima pagina"
                variant="outline"
                size="sm"
                borderRadius="lg"
                isDisabled={page >= totalPages}
                onClick={handleNext}
                icon={
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                }
              />
            </HStack>
          )}
        </>
      )}
    </Box>
  );
}
