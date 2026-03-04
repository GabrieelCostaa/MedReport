import { useState, useRef, useEffect } from 'react';
import {
  Box,
  Button,
  HStack,
  Input,
  VStack,
  Text,
  useToast,
} from '@chakra-ui/react';
import { aiAssistantApi } from '../api/ai-assistant';

type Message = { role: 'user' | 'assistant'; content: string };

interface ReportAssistantProps {
  onReportCreated: (reportId: string) => void;
}

export default function ReportAssistant({ onReportCreated }: ReportAssistantProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content:
        'Olá. Sou o assistente para criação de relatórios de solicitação de cirurgia. Informe o CID, diagnóstico, descrição da cirurgia e materiais necessários. Vou sugerir códigos TUSS e montar o relatório.',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const toast = useToast();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', content: text }]);
    setLoading(true);
    try {
      const res = await aiAssistantApi.chat(text);
      setMessages((m) => [...m, { role: 'assistant', content: res.reply }]);
      if (res.report_id) {
        toast({ title: 'Relatório criado pelo assistente', status: 'success' });
        onReportCreated(res.report_id);
      }
    } catch {
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: 'Desculpe, ocorreu um erro. Tente novamente ou use o formulário.',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box maxW="2xl">
      <VStack
        align="stretch"
        bg="gray.50"
        p={4}
        borderRadius="lg"
        h="400px"
        overflowY="auto"
        spacing={3}
      >
        {messages.map((msg, i) => (
          <Box
            key={i}
            alignSelf={msg.role === 'user' ? 'flex-end' : 'flex-start'}
            bg={msg.role === 'user' ? 'brand.500' : 'white'}
            color={msg.role === 'user' ? 'white' : 'gray.800'}
            px={4}
            py={2}
            borderRadius="lg"
            maxW="85%"
          >
            <Text fontSize="sm" whiteSpace="pre-wrap">
              {msg.content}
            </Text>
          </Box>
        ))}
        <div ref={bottomRef} />
      </VStack>
      <HStack mt={3} gap={2}>
        <Input
          placeholder="Digite sua mensagem..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
        />
        <Button colorScheme="green" onClick={handleSend} isLoading={loading}>
          Enviar
        </Button>
      </HStack>
    </Box>
  );
}
