import { useEffect, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import {
  Box,
  Button,
  Heading,
  Text,
  VStack,
  HStack,
  SimpleGrid,
  Badge,
  Skeleton,
} from '@chakra-ui/react';
import { reportsApi, type Report } from '../api/reports';

function StatCard({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <Box p={5} bg="white" borderRadius="xl" border="1px solid" borderColor="gray.100">
      <Text fontSize="xs" fontWeight="600" color="gray.500" textTransform="uppercase" letterSpacing="wider">
        {label}
      </Text>
      <Text fontSize="2xl" fontWeight="700" color={color} mt={1}>
        {value}
      </Text>
    </Box>
  );
}

export default function Home() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    reportsApi
      .listAll()
      .then((res) => setReports(res?.items || []))
      .catch(() => setReports([]))
      .finally(() => setLoading(false));
  }, []);

  const total = reports.length;
  const signed = reports.filter(r => r.status === 'signed').length;
  const drafts = total - signed;

  const recentReports = reports.slice(0, 5);

  return (
    <Box>
      {/* Welcome */}
      <Box mb={8}>
        <Heading size="lg" fontWeight="700" color="gray.800">
          Bom dia, Dr.
        </Heading>
        <Text color="gray.500" mt={1}>
          Crie justificativas tecnicas com inteligencia artificial em minutos.
        </Text>
      </Box>

      {/* Quick Action */}
      <Box
        p={6}
        mb={8}
        bg="linear-gradient(135deg, #0d9488 0%, #0f766e 100%)"
        borderRadius="xl"
        color="white"
      >
        <HStack justify="space-between" align="center" flexWrap="wrap" gap={4}>
          <Box>
            <Text fontSize="lg" fontWeight="600">
              Novo Relatorio OPME
            </Text>
            <Text fontSize="sm" opacity={0.85} mt={1}>
              Gere uma justificativa tecnica completa com IA, referencias PubMed e conformidade ANS.
            </Text>
          </Box>
          <Button
            as={RouterLink}
            to="/dashboard/reports/new"
            size="lg"
            bg="white"
            color="brand.700"
            fontWeight="600"
            _hover={{ bg: 'whiteAlpha.900' }}
            borderRadius="lg"
            leftIcon={
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M12 5v14M5 12h14" />
              </svg>
            }
          >
            Criar Relatorio
          </Button>
        </HStack>
      </Box>

      {/* Stats */}
      <SimpleGrid columns={{ base: 1, sm: 3 }} gap={4} mb={8}>
        {loading ? (
          <>
            {[1, 2, 3].map(i => (
              <Box key={i} p={5} bg="white" borderRadius="xl" border="1px solid" borderColor="gray.100">
                <Skeleton h="10px" w="80px" mb={3} />
                <Skeleton h="28px" w="40px" />
              </Box>
            ))}
          </>
        ) : (
          <>
            <StatCard label="Total de Relatorios" value={total} color="gray.800" />
            <StatCard label="Assinados" value={signed} color="green.600" />
            <StatCard label="Rascunhos" value={drafts} color="yellow.600" />
          </>
        )}
      </SimpleGrid>

      {/* Recent Reports */}
      <Box>
        <HStack justify="space-between" mb={4}>
          <Heading size="sm" fontWeight="600" color="gray.700">
            Relatorios Recentes
          </Heading>
          <Button as={RouterLink} to="/dashboard/reports" variant="ghost" size="sm" color="brand.600" fontWeight="500">
            Ver todos
          </Button>
        </HStack>

        {loading ? (
          <VStack align="stretch" gap={2}>
            {[1, 2, 3].map(i => (
              <Box key={i} p={4} bg="white" borderRadius="lg" border="1px solid" borderColor="gray.100">
                <HStack justify="space-between">
                  <Box flex={1}>
                    <Skeleton h="14px" w="60%" mb={2} />
                    <Skeleton h="10px" w="30%" />
                  </Box>
                  <Skeleton h="20px" w="70px" borderRadius="full" />
                </HStack>
              </Box>
            ))}
          </VStack>
        ) : recentReports.length === 0 ? (
          <Box p={8} bg="white" borderRadius="xl" border="1px solid" borderColor="gray.100" textAlign="center">
            <Text color="gray.400" mb={3}>Nenhum relatorio criado ainda</Text>
            <Button as={RouterLink} to="/dashboard/reports/new" colorScheme="brand" size="sm">
              Criar primeiro relatorio
            </Button>
          </Box>
        ) : (
          <VStack align="stretch" gap={2}>
            {recentReports.map((r) => (
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
                <HStack justify="space-between">
                  <Box>
                    <Text fontSize="sm" fontWeight="500" color="gray.800">
                      {r.patient_diagnosis || 'Relatorio #' + r.id.slice(0, 8)}
                    </Text>
                    <Text fontSize="xs" color="gray.400" mt={1}>
                      {new Date(r.created_at).toLocaleDateString('pt-BR', {
                        day: '2-digit', month: 'short', year: 'numeric',
                      })}
                    </Text>
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
        )}
      </Box>
    </Box>
  );
}
