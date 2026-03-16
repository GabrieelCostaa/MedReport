import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Text,
  VStack,
  HStack,
  Flex,
  useToast,
  Badge,
  SimpleGrid,
  Spinner,
  Icon,
} from '@chakra-ui/react';
import { FiArrowLeft, FiDownload, FiFileText, FiEdit3 } from 'react-icons/fi';
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

const buttonTransition = 'all 0.3s cubic-bezier(0.65, 0.05, 0, 1)';
const buttonHover = { transform: 'translateY(-2px)', shadow: 'lg' };

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

  const handleDownload = async (format: 'pdf' | 'docx' | 'xml') => {
    if (!id) return;
    const labels = { pdf: 'PDF', docx: 'DOCX', xml: 'XML' };
    try {
      let blob: Blob;
      let filename: string;
      if (format === 'pdf') {
        blob = await reportsApi.downloadPdf(id);
        filename = `relatorio-${id}.pdf`;
      } else if (format === 'docx') {
        blob = await reportsApi.downloadDocx(id);
        filename = `relatorio-${id}.docx`;
      } else {
        blob = await reportsApi.downloadXml(id);
        filename = `guia-tiss-${id}.xml`;
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast({ title: `Erro ao baixar ${labels[format]}`, status: 'error' });
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

  if (loading) {
    return (
      <Flex justify="center" align="center" minH="200px">
        <Spinner size="lg" color="brand.500" />
      </Flex>
    );
  }

  if (!report) {
    return (
      <Flex justify="center" align="center" minH="200px">
        <Text color="text.muted">Relatório não encontrado</Text>
      </Flex>
    );
  }

  return (
    <Flex justify="center" w="100%">
      <VStack gap={6} align="stretch" maxW="3xl" w="100%" mx="auto">
        {/* Header */}
        <HStack justify="space-between" flexWrap="wrap" gap={3}>
          <Box>
            <Text fontSize="xl" fontWeight="700" color="text.primary">
              Revisão do Relatório
            </Text>
            <HStack mt={2} gap={3}>
              <Badge
                colorScheme={report.status === 'signed' ? 'green' : 'yellow'}
                fontSize="xs"
                borderRadius="full"
                px={2}
                py={0.5}
              >
                {report.status === 'signed' ? 'Assinado' : 'Rascunho'}
              </Badge>
              <Text fontSize="xs" color="text.subtle">
                Criado em {new Date(report.created_at).toLocaleDateString('pt-BR', {
                  day: '2-digit', month: 'short', year: 'numeric',
                  hour: '2-digit', minute: '2-digit',
                })}
              </Text>
            </HStack>
          </Box>
          <Button
            variant="ghost" size="sm" color="text.muted"
            leftIcon={<Icon as={FiArrowLeft} />}
            onClick={() => navigate('/dashboard/reports')}
          >
            Voltar aos documentos
          </Button>
        </HStack>

        {/* Report details card */}
        <Box bg="surface" borderRadius="xl" border="1px solid" borderColor="border.subtle" p={6} shadow="sm">
          <SimpleGrid columns={{ base: 1, sm: 2 }} spacingY={4} spacingX={8}>
            <Box>
              <Text fontSize="xs" fontWeight="600" color="text.muted" textTransform="uppercase" letterSpacing="wider" mb={1}>
                CID
              </Text>
              <Text fontSize="sm" fontWeight="500" color="text.primary">{report.cid ?? '-'}</Text>
            </Box>
            <Box>
              <Text fontSize="xs" fontWeight="600" color="text.muted" textTransform="uppercase" letterSpacing="wider" mb={1}>
                Convênio
              </Text>
              <Text fontSize="sm" fontWeight="500" color="text.primary">{report.health_plan ?? 'Não informado'}</Text>
            </Box>
            <Box>
              <Text fontSize="xs" fontWeight="600" color="text.muted" textTransform="uppercase" letterSpacing="wider" mb={1}>
                Diagnóstico
              </Text>
              <Text fontSize="sm" color="text.primary">{report.diagnosis ?? '-'}</Text>
            </Box>
            <Box>
              <Text fontSize="xs" fontWeight="600" color="text.muted" textTransform="uppercase" letterSpacing="wider" mb={1}>
                Procedimento
              </Text>
              <Text fontSize="sm" color="text.primary">{report.surgery_description ?? '-'}</Text>
            </Box>
            <Box gridColumn={{ sm: 'span 2' }}>
              <Text fontSize="xs" fontWeight="600" color="text.muted" textTransform="uppercase" letterSpacing="wider" mb={1}>
                Materiais OPME
              </Text>
              <Text fontSize="sm" color="text.primary">{report.materials ?? '-'}</Text>
            </Box>
          </SimpleGrid>
        </Box>

        {/* Inconsistencies */}
        {report.inconsistencies && report.inconsistencies.length > 0 && (
          <Box p={4} bg="orange.50" borderRadius="xl" border="1px solid" borderColor="orange.200">
            <Text fontWeight="600" fontSize="sm" color="orange.800" mb={2}>
              Inconsistências TUSS
            </Text>
            <VStack align="stretch" gap={1}>
              {report.inconsistencies.map((inc, i) => (
                <Text key={i} fontSize="sm" color="orange.700">
                  {inc.field}: {inc.message}
                </Text>
              ))}
            </VStack>
          </Box>
        )}

        {/* Download actions */}
        <Box bg="surface" borderRadius="xl" border="1px solid" borderColor="border.subtle" p={6} shadow="sm">
          <Text fontSize="xs" fontWeight="600" color="text.muted" textTransform="uppercase" letterSpacing="wider" mb={4}>
            Downloads
          </Text>
          <HStack gap={3} flexWrap="wrap">
            <Button
              onClick={() => handleDownload('pdf')}
              variant="outline" size="sm" borderRadius="lg"
              leftIcon={<Icon as={FiDownload} />}
              transition={buttonTransition}
              _hover={buttonHover}
            >
              Baixar PDF
            </Button>
            <Button
              onClick={() => handleDownload('docx')}
              variant="outline" size="sm" borderRadius="lg"
              leftIcon={<Icon as={FiFileText} />}
              transition={buttonTransition}
              _hover={buttonHover}
            >
              Baixar Word
            </Button>
            <Button
              onClick={() => handleDownload('xml')}
              variant="outline" size="sm" borderRadius="lg"
              leftIcon={<Icon as={FiEdit3} />}
              transition={buttonTransition}
              _hover={buttonHover}
            >
              Baixar XML (TISS)
            </Button>
            {report.status !== 'signed' && (
              <Button
                colorScheme="brand" onClick={handleSign} isLoading={signing}
                size="sm" borderRadius="lg" fontWeight="600"
                transition={buttonTransition}
                _hover={buttonHover}
              >
                Assinar digitalmente
              </Button>
            )}
          </HStack>
        </Box>
      </VStack>
    </Flex>
  );
}
