import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Heading,
  Text,
  VStack,
  useToast,
  Badge,
  HStack,
} from '@chakra-ui/react';
import { reportsApi } from '../api/reports';

type ReportDetail = {
  id: string;
  status: string;
  cid?: string;
  diagnosis?: string;
  surgery_description?: string;
  materials?: string;
  health_plan?: string;
  created_at: string;
  inconsistencies?: { field: string; message: string }[];
};

export default function ReportReview() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [signing, setSigning] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();

  useEffect(() => {
    if (!id) return;
    reportsApi
      .get(id)
      .then(setReport)
      .catch(() => setReport(null))
      .finally(() => setLoading(false));
  }, [id]);

  const handleDownloadPdf = async () => {
    if (!id) return;
    try {
      const blob = await reportsApi.downloadPdf(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `relatorio-${id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast({ title: 'Erro ao baixar PDF', status: 'error' });
    }
  };

  const handleDownloadXml = async () => {
    if (!id) return;
    try {
      const blob = await reportsApi.downloadXml(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `guia-tiss-${id}.xml`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast({ title: 'Erro ao baixar XML', status: 'error' });
    }
  };

  const handleDownloadDocx = async () => {
    if (!id) return;
    try {
      const blob = await reportsApi.downloadDocx(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `relatorio-${id}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast({ title: 'Erro ao baixar DOCX', status: 'error' });
    }
  };

  const handleSign = async () => {
    if (!id) return;
    setSigning(true);
    try {
      await reportsApi.sign(id);
      toast({ title: 'Relatório assinado', status: 'success' });
      setReport((p) => (p ? { ...p, status: 'signed' } : null));
    } catch {
      toast({ title: 'Erro ao assinar (integre ICP-Brasil)', status: 'error' });
    } finally {
      setSigning(false);
    }
  };

  if (loading || !report) {
    return <Box>Carregando...</Box>;
  }

  return (
    <Box>
      <Heading size="md" mb={4}>
        Revisão do relatório
      </Heading>
      <HStack mb={4}>
        <Badge colorScheme={report.status === 'signed' ? 'green' : 'yellow'} fontSize="md">
          {report.status}
        </Badge>
        <Text fontSize="sm" color="gray.500">
          Criado em {new Date(report.created_at).toLocaleString('pt-BR')}
        </Text>
      </HStack>
      <VStack align="stretch" gap={3} maxW="2xl" mb={6}>
        <Box>
          <Text fontWeight="bold">CID</Text>
          <Text>{report.cid ?? '-'}</Text>
        </Box>
        <Box>
          <Text fontWeight="bold">Diagnóstico</Text>
          <Text>{report.diagnosis ?? '-'}</Text>
        </Box>
        <Box>
          <Text fontWeight="bold">Descrição da cirurgia</Text>
          <Text>{report.surgery_description ?? '-'}</Text>
        </Box>
        <Box>
          <Text fontWeight="bold">Materiais</Text>
          <Text>{report.materials ?? '-'}</Text>
        </Box>
        <Box>
          <Text fontWeight="bold">Convênio</Text>
          <Text>{report.health_plan ?? '-'}</Text>
        </Box>
      </VStack>
      {report.inconsistencies && report.inconsistencies.length > 0 && (
        <Box p={4} bg="orange.50" borderRadius="md" mb={6}>
          <Heading size="sm" mb={2}>
            Inconsistências TUSS
          </Heading>
          <VStack align="stretch">
            {report.inconsistencies.map((inc, i) => (
              <Text key={i} fontSize="sm">
                {inc.field}: {inc.message}
              </Text>
            ))}
          </VStack>
        </Box>
      )}
      <HStack gap={3}>
        <Button onClick={handleDownloadPdf} variant="outline">
          Baixar PDF
        </Button>
        <Button onClick={handleDownloadDocx} variant="outline">
          Baixar Word
        </Button>
        <Button onClick={handleDownloadXml} variant="outline">
          Baixar XML (TISS)
        </Button>
        {report.status !== 'signed' && (
          <Button colorScheme="green" onClick={handleSign} isLoading={signing}>
            Assinar digitalmente
          </Button>
        )}
        <Button variant="ghost" onClick={() => navigate('/reports')}>
          Voltar
        </Button>
      </HStack>
    </Box>
  );
}
