import { useEffect, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import {
  Box,
  Button,
  Heading,
  Link,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
} from '@chakra-ui/react';
import { reportsApi } from '../api/reports';

type Report = {
  id: string;
  status: string;
  created_at: string;
  patient_diagnosis?: string;
};

export default function ReportList() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    reportsApi
      .list()
      .then(setReports)
      .catch(() => setReports([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Box>
      <Heading size="md" mb={4}>
        Relatórios de Solicitação de Cirurgia
      </Heading>
      <Button as={RouterLink} to="/reports/new" colorScheme="green" mb={4}>
        Novo relatório
      </Button>
      {loading ? (
        <p>Carregando...</p>
      ) : (
        <Table variant="simple">
          <Thead>
            <Tr>
              <Th>ID</Th>
              <Th>Status</Th>
              <Th>Diagnóstico</Th>
              <Th>Data</Th>
              <Th></Th>
            </Tr>
          </Thead>
          <Tbody>
            {reports.map((r) => (
              <Tr key={r.id}>
                <Td>{r.id.slice(0, 8)}</Td>
                <Td>
                  <Badge colorScheme={r.status === 'signed' ? 'green' : 'yellow'}>
                    {r.status}
                  </Badge>
                </Td>
                <Td>{r.patient_diagnosis ?? '-'}</Td>
                <Td>{new Date(r.created_at).toLocaleDateString('pt-BR')}</Td>
                <Td>
                  <Link as={RouterLink} to={`/reports/${r.id}/review`} color="brand.600">
                    Ver / Revisar
                  </Link>
                </Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      )}
      {!loading && reports.length === 0 && (
        <Box py={8} textAlign="center" color="gray.500">
          Nenhum relatório ainda. Crie o primeiro.
        </Box>
      )}
    </Box>
  );
}
