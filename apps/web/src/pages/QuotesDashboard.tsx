import { useEffect, useState } from 'react';
import {
  Box,
  Heading,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
  Input,
  HStack,
  Button,
  Select,
} from '@chakra-ui/react';
import { quotesApi } from '../api/quotes';

type Quote = {
  id: string;
  external_id: string;
  portal: string;
  description: string;
  status: string;
  deadline?: string;
  created_at: string;
};

export default function QuotesDashboard() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterPortal, setFilterPortal] = useState('');
  const [filterStatus, setFilterStatus] = useState('');

  useEffect(() => {
    quotesApi
      .list({ portal: filterPortal || undefined, status: filterStatus || undefined })
      .then((r) => setQuotes(r.items ?? []))
      .catch(() => setQuotes([]))
      .finally(() => setLoading(false));
  }, [filterPortal, filterStatus]);

  return (
    <Box>
      <Heading size="md" mb={4}>
        Central de cotações
      </Heading>
      <HStack mb={4} gap={4}>
        <Input
          placeholder="Filtrar por portal"
          value={filterPortal}
          onChange={(e) => setFilterPortal(e.target.value)}
          maxW="xs"
        />
        <Select
          placeholder="Status"
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          maxW="xs"
        >
          <option value="pending">Pendente</option>
          <option value="sent">Enviado</option>
          <option value="won">Ganho</option>
          <option value="lost">Perdido</option>
        </Select>
        <Button size="sm" onClick={() => setLoading(true)}>
          Atualizar
        </Button>
      </HStack>
      {loading ? (
        <p>Carregando...</p>
      ) : (
        <Table variant="simple">
          <Thead>
            <Tr>
              <Th>Portal</Th>
              <Th>Descrição</Th>
              <Th>Status</Th>
              <Th>Prazo</Th>
              <Th>Data</Th>
            </Tr>
          </Thead>
          <Tbody>
            {quotes.map((q) => (
              <Tr key={q.id}>
                <Td>{q.portal}</Td>
                <Td>{q.description?.slice(0, 50) ?? '-'}</Td>
                <Td>
                  <Badge colorScheme={q.status === 'sent' ? 'green' : 'yellow'}>
                    {q.status}
                  </Badge>
                </Td>
                <Td>{q.deadline ? new Date(q.deadline).toLocaleDateString('pt-BR') : '-'}</Td>
                <Td>{new Date(q.created_at).toLocaleDateString('pt-BR')}</Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      )}
      {!loading && quotes.length === 0 && (
        <Box py={8} textAlign="center" color="gray.500">
          Nenhuma cotação encontrada. Configure os robôs RPA para coletar cotações dos portais.
        </Box>
      )}
    </Box>
  );
}
