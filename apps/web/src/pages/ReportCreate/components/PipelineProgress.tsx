import { useState, useEffect, useRef } from 'react';
import { Box, HStack, VStack, Text, Flex } from '@chakra-ui/react';
import { pulse, fadeInUp, spinSlow, shimmer } from '../animations';
import TypewriterLine from './TypewriterLine';

const STAGES = [
  { key: 'researching', label: 'Pesquisa', sublabel: 'Buscando evidências' },
  { key: 'writing', label: 'Redação', sublabel: 'Gerando justificativa' },
  { key: 'auditing', label: 'Auditoria', sublabel: 'Verificando conformidade' },
  { key: 'validating', label: 'Validação', sublabel: 'Checklist final' },
];

interface PipelineProgressProps {
  messages: string[];
  currentStage: string;
}

export default function PipelineProgress({ messages, currentStage }: PipelineProgressProps) {
  const [typingIdx, setTypingIdx] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setTypingIdx(Math.max(0, messages.length - 1));
  }, [messages.length]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [typingIdx, messages.length]);

  const completedMessages = messages.slice(0, typingIdx);
  const currentMessage = messages[typingIdx] || '';
  const currentIdx = STAGES.findIndex((s) => s.key === currentStage);
  const activeStage = STAGES[currentIdx] || STAGES[0];

  return (
    <Box py={8} maxW="2xl" mx="auto">
      {/* Stage progress — horizontal steps */}
      <Flex mb={8} justify="center" align="flex-start" gap={0}>
        {STAGES.map((stage, i) => {
          const isActive = i === currentIdx;
          const isDone = i < currentIdx;
          return (
            <Flex key={stage.key} align="center">
              <Flex direction="column" align="center" minW="80px">
                {/* Circle indicator */}
                <Flex
                  w="36px" h="36px" borderRadius="full" align="center" justify="center"
                  border="2px solid"
                  borderColor={isDone ? 'green.500' : isActive ? 'blue.500' : 'gray.200'}
                  bg={isDone ? 'green.500' : isActive ? 'blue.500' : 'white'}
                  color={isDone || isActive ? 'white' : 'gray.400'}
                  fontSize="sm" fontWeight="600"
                  transition="all 0.4s ease"
                  position="relative"
                >
                  {isDone ? (
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path d="M2 7L5.5 10.5L12 3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  ) : (
                    <Text fontSize="sm">{i + 1}</Text>
                  )}
                  {/* Pulse ring for active */}
                  {isActive && (
                    <Box
                      position="absolute" inset="-4px" borderRadius="full"
                      border="2px solid" borderColor="blue.300"
                      sx={{ animation: `${pulse} 2s ease-in-out infinite` }}
                    />
                  )}
                </Flex>
                {/* Label */}
                <Text
                  fontSize="xs" fontWeight={isActive ? '600' : '400'} mt={2}
                  color={isDone ? 'green.600' : isActive ? 'blue.600' : 'gray.400'}
                  transition="all 0.3s"
                >
                  {stage.label}
                </Text>
              </Flex>
              {/* Connector line */}
              {i < STAGES.length - 1 && (
                <Box
                  w="48px" h="2px" mt="-18px"
                  bg={isDone ? 'green.400' : 'gray.200'}
                  transition="background 0.4s ease"
                  borderRadius="full"
                />
              )}
            </Flex>
          );
        })}
      </Flex>

      {/* Active stage header */}
      <HStack
        mb={5} px={4} py={3} gap={3} justify="center"
        bg="gray.50" borderRadius="lg" border="1px solid" borderColor="gray.100"
      >
        {/* Spinning indicator */}
        <Box
          w="18px" h="18px" borderRadius="full"
          border="2px solid" borderColor="blue.500"
          borderTopColor="transparent"
          sx={{ animation: `${spinSlow} 1s linear infinite` }}
        />
        <Box>
          <Text fontSize="sm" fontWeight="600" color="gray.700">
            {activeStage.label}
          </Text>
          <Text fontSize="xs" color="gray.500">
            {activeStage.sublabel}
          </Text>
        </Box>
      </HStack>

      {/* Console-style message log */}
      <Box
        bg="gray.900" borderRadius="lg" overflow="hidden"
        border="1px solid" borderColor="gray.700"
      >
        {/* Terminal header bar */}
        <HStack px={4} py={2} bg="gray.800" gap={2}>
          <Box w="8px" h="8px" borderRadius="full" bg="red.400" />
          <Box w="8px" h="8px" borderRadius="full" bg="yellow.400" />
          <Box w="8px" h="8px" borderRadius="full" bg="green.400" />
          <Text fontSize="2xs" color="gray.500" ml={2} fontFamily="mono">
            medreport — pipeline
          </Text>
        </HStack>

        {/* Messages area */}
        <Box px={4} py={3} maxH="240px" overflowY="auto" position="relative">
          {/* Shimmer overlay while processing */}
          <Box
            position="absolute" top={0} left={0} right={0} h="2px"
            bgGradient="linear(to-r, transparent, blue.400, transparent)"
            bgSize="200% 100%"
            sx={{ animation: `${shimmer} 2s linear infinite` }}
          />

          <VStack align="stretch" gap={0}>
            {completedMessages.map((msg, i) => (
              <HStack
                key={i} py="4px" gap={2}
                sx={{ animation: `${fadeInUp} 0.2s ease both` }}
              >
                <Text fontSize="2xs" color="gray.600" fontFamily="mono" flexShrink={0}>
                  {String(i + 1).padStart(2, '0')}
                </Text>
                <Text fontSize="xs" color="gray.400" fontFamily="mono" lineHeight="tall">
                  {msg}
                </Text>
              </HStack>
            ))}
            {currentMessage && (
              <HStack py="4px" gap={2}>
                <Text fontSize="2xs" color="blue.400" fontFamily="mono" flexShrink={0}>
                  {String(completedMessages.length + 1).padStart(2, '0')}
                </Text>
                <TypewriterLine text={currentMessage} onComplete={() => {
                  if (typingIdx < messages.length - 1) {
                    setTypingIdx((p) => p + 1);
                  }
                }} />
              </HStack>
            )}
            <Box ref={bottomRef} />
          </VStack>
        </Box>
      </Box>

      {/* Processing indicator */}
      <HStack justify="center" mt={4} gap={2}>
        <Box
          w="6px" h="6px" borderRadius="full" bg="blue.400"
          sx={{ animation: `${pulse} 1.5s ease-in-out infinite` }}
        />
        <Text fontSize="xs" color="gray.400">
          Processando — isso pode levar alguns segundos
        </Text>
      </HStack>
    </Box>
  );
}
