import {
  VStack,
  HStack,
  Box,
  Flex,
  Text,
  Button,
  Alert,
  AlertIcon,
  SimpleGrid,
  Icon,
} from '@chakra-ui/react';
import { FiArrowLeft, FiFileText } from 'react-icons/fi';
import { fadeInUp } from '../animations';
import type { Product } from '../types';

interface StepRevisaoProps {
  approved: boolean;
  pacienteNome: string;
  cid: string;
  selectedProduct: Product | null;
  healthPlan: string;
  justificativa: string;
  onBack: () => void;
  onGoToReview: () => void;
}

const buttonTransition = 'all 0.3s cubic-bezier(0.65, 0.05, 0, 1)';
const buttonHover = { transform: 'translateY(-2px)', shadow: 'lg' };

export default function StepRevisao({
  approved,
  pacienteNome,
  cid,
  selectedProduct,
  healthPlan,
  justificativa,
  onBack,
  onGoToReview,
}: StepRevisaoProps) {
  return (
    <Flex justify="center" w="full">
      <VStack
        gap={6}
        align="stretch"
        maxW="3xl"
        w="full"
        mx="auto"
        sx={{ animation: `${fadeInUp} 0.4s ease both` }}
      >
        {/* Header */}
        <Box>
          <Text
            fontSize="xs"
            fontWeight="600"
            color="text.muted"
            textTransform="uppercase"
            letterSpacing="wider"
          >
            Passo 4
          </Text>
          <Text fontSize="xl" fontWeight="700" color="text.primary">
            Revisão Final
          </Text>
        </Box>

        {/* Status alert */}
        <Alert
          status={approved ? 'success' : 'warning'}
          borderRadius="lg"
          variant="subtle"
        >
          <AlertIcon />
          <Text fontSize="sm">
            {approved
              ? 'Relatório aprovado pelo checklist. Pronto para download.'
              : 'Checklist incompleto. O relatório pode necessitar de ajustes.'}
          </Text>
        </Alert>

        {/* Patient info card */}
        <Box
          bg="surface"
          border="1px solid"
          borderColor="border.subtle"
          borderRadius="xl"
          p={6}
          shadow="sm"
        >
          <SimpleGrid columns={{ base: 1, sm: 2 }} spacingY={4} spacingX={8}>
            <Box>
              <Text
                fontSize="xs"
                fontWeight="600"
                color="text.muted"
                textTransform="uppercase"
                letterSpacing="wider"
                mb={1}
              >
                Paciente
              </Text>
              <Text fontSize="sm" color="text.primary" fontWeight="500">
                {pacienteNome}
              </Text>
            </Box>

            <Box>
              <Text
                fontSize="xs"
                fontWeight="600"
                color="text.muted"
                textTransform="uppercase"
                letterSpacing="wider"
                mb={1}
              >
                CID
              </Text>
              <Text fontSize="sm" color="text.primary" fontWeight="500">
                {cid}
              </Text>
            </Box>

            <Box>
              <Text
                fontSize="xs"
                fontWeight="600"
                color="text.muted"
                textTransform="uppercase"
                letterSpacing="wider"
                mb={1}
              >
                Material
              </Text>
              <Text fontSize="sm" color="text.primary" fontWeight="500">
                {selectedProduct?.nome}
              </Text>
            </Box>

            <Box>
              <Text
                fontSize="xs"
                fontWeight="600"
                color="text.muted"
                textTransform="uppercase"
                letterSpacing="wider"
                mb={1}
              >
                Convênio
              </Text>
              <Text fontSize="sm" color="text.primary" fontWeight="500">
                {healthPlan || 'Não informado'}
              </Text>
            </Box>
          </SimpleGrid>
        </Box>

        {/* Justificativa card — expands with content, no scroll */}
        <Box
          bg="surface"
          border="1px solid"
          borderColor="border.subtle"
          borderRadius="xl"
          p={6}
          shadow="sm"
        >
          <Text
            fontSize="xs"
            fontWeight="600"
            color="text.muted"
            textTransform="uppercase"
            letterSpacing="wider"
            mb={3}
          >
            Justificativa Técnica
          </Text>
          <Text fontSize="sm" color="text.secondary" whiteSpace="pre-wrap" lineHeight="tall">
            {justificativa}
          </Text>
        </Box>

        {/* Actions */}
        <HStack justify="flex-end" pt={2} spacing={3}>
          <Button
            variant="outline"
            onClick={onBack}
            leftIcon={<Icon as={FiArrowLeft} />}
            transition={buttonTransition}
            _hover={buttonHover}
          >
            Voltar para Edição
          </Button>
          <Button
            colorScheme="brand"
            onClick={onGoToReview}
            leftIcon={<Icon as={FiFileText} />}
            transition={buttonTransition}
            _hover={buttonHover}
          >
            Abrir Revisão & Download PDF
          </Button>
        </HStack>
      </VStack>
    </Flex>
  );
}
