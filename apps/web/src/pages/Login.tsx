import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Input,
  VStack,
  Heading,
  useToast,
} from '@chakra-ui/react';
import { authApi } from '../api/auth';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await authApi.login(email, password);
      localStorage.setItem('token', res.access_token);
      localStorage.setItem('user', JSON.stringify(res.user));
      toast({ title: 'Login realizado', status: 'success' });
      navigate(res.user.legal_basis_acknowledged ? '/reports' : '/legal-basis');
    } catch (err: unknown) {
      toast({
        title: 'Erro no login',
        description: (err as { message?: string })?.message ?? 'Tente novamente.',
        status: 'error',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box maxW="md" mx="auto" mt={20} p={8} bg="white" borderRadius="lg" shadow="md">
      <Heading size="lg" mb={6} color="brand.600">
        Entrar
      </Heading>
      <form onSubmit={handleSubmit}>
        <VStack gap={4} align="stretch">
          <FormControl isRequired>
            <FormLabel>E-mail</FormLabel>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="seu@email.com"
            />
          </FormControl>
          <FormControl isRequired>
            <FormLabel>Senha</FormLabel>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </FormControl>
          <Button type="submit" colorScheme="green" isLoading={loading} w="full">
            Entrar
          </Button>
        </VStack>
      </form>
    </Box>
  );
}
