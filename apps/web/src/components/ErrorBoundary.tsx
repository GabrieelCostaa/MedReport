import { Component, type ReactNode } from 'react';
import { Box, Button, Text, VStack, Icon } from '@chakra-ui/react';
import { FiAlertTriangle } from 'react-icons/fi';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  handleGoHome = () => {
    window.location.href = '/dashboard';
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <Box minH="100vh" display="flex" alignItems="center" justifyContent="center" bg="#f8fafc" p={4}>
        <VStack gap={4} maxW="md" textAlign="center">
          <Icon as={FiAlertTriangle} boxSize={12} color="orange.400" />
          <Text fontSize="xl" fontWeight="700" color="gray.800">
            Algo deu errado
          </Text>
          <Text fontSize="sm" color="gray.500">
            Ocorreu um erro inesperado. Tente recarregar a pagina ou voltar ao inicio.
          </Text>
          {this.state.error && (
            <Box
              p={3} bg="red.50" borderRadius="md" border="1px solid"
              borderColor="red.200" w="100%" maxH="120px" overflow="auto"
            >
              <Text fontSize="xs" color="red.600" fontFamily="mono">
                {this.state.error.message}
              </Text>
            </Box>
          )}
          <Box display="flex" gap={3}>
            <Button size="sm" variant="outline" onClick={this.handleReset}>
              Tentar novamente
            </Button>
            <Button size="sm" colorScheme="brand" onClick={this.handleGoHome}>
              Voltar ao inicio
            </Button>
          </Box>
        </VStack>
      </Box>
    );
  }
}
