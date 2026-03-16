import { useState, useEffect, useRef, useMemo } from 'react';
import { Box, HStack, Text, Flex } from '@chakra-ui/react';
import { cursorBlink, pulse, shimmer, fadeInUp } from '../animations';

interface TextRevealProps {
  text: string;
  onComplete: () => void;
}

const CIPHER_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@#$%&*!?<>{}[]=/\\';
const SCRAMBLE_LENGTH = 30; // how many chars ahead get scrambled

function randomChar() {
  return CIPHER_CHARS[Math.floor(Math.random() * CIPHER_CHARS.length)];
}

export default function TextReveal({ text, onComplete }: TextRevealProps) {
  const chars = useMemo(() => text.split(''), [text]);
  const [revealedCount, setRevealedCount] = useState(0);
  const [scrambleTick, setScrambleTick] = useState(0);
  const doneRef = useRef(false);

  useEffect(() => {
    setRevealedCount(0);
    doneRef.current = false;

    // Reveal ~4 chars every 25ms
    const revealTimer = setInterval(() => {
      setRevealedCount((prev) => {
        const next = prev + 4;
        if (next >= chars.length) {
          clearInterval(revealTimer);
          if (!doneRef.current) {
            doneRef.current = true;
            setTimeout(onComplete, 400);
          }
          return chars.length;
        }
        return next;
      });
    }, 25);

    // Scramble animation ticks faster for fluid randomness
    const scrambleTimer = setInterval(() => {
      setScrambleTick((t) => t + 1);
    }, 40);

    return () => {
      clearInterval(revealTimer);
      clearInterval(scrambleTimer);
    };
  }, [text, chars.length, onComplete]);

  const isComplete = revealedCount >= chars.length;
  const progress = Math.min(100, Math.round((revealedCount / chars.length) * 100));

  // Build displayed text: revealed + scrambled zone + hidden
  const displayedText = useMemo(() => {
    if (isComplete) return text;

    const revealed = text.slice(0, revealedCount);
    const scrambleEnd = Math.min(revealedCount + SCRAMBLE_LENGTH, chars.length);
    let scrambled = '';
    for (let i = revealedCount; i < scrambleEnd; i++) {
      // Keep whitespace/newlines as-is for readability
      if (chars[i] === ' ' || chars[i] === '\n') {
        scrambled += chars[i];
      } else {
        scrambled += randomChar();
      }
    }
    return revealed + scrambled;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revealedCount, scrambleTick, isComplete, text, chars]);

  return (
    <Flex justify="center" w="100%">
      <Box py={6} w="100%" maxW="3xl" sx={{ animation: `${fadeInUp} 0.4s ease both` }}>
        {/* Header with status */}
        <HStack mb={4} justify="space-between" align="center">
          <HStack gap={2}>
            {!isComplete && (
              <Box
                w="6px" h="6px" borderRadius="full" bg="brand.500"
                sx={{ animation: `${pulse} 1.5s ease-in-out infinite` }}
              />
            )}
            {isComplete && (
              <Flex w="18px" h="18px" borderRadius="full" bg="brand.500" align="center" justify="center">
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path d="M1.5 5L4 7.5L8.5 2.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </Flex>
            )}
            <Text
              fontSize="xs" color={isComplete ? 'brand.600' : 'text.muted'} fontWeight="600"
              textTransform="uppercase" letterSpacing="wider"
            >
              {isComplete ? 'Justificativa gerada' : 'Redigindo justificativa'}
            </Text>
          </HStack>
          {!isComplete && (
            <Text fontSize="xs" color="text.subtle" fontFamily="mono">{progress}%</Text>
          )}
        </HStack>

        {/* Progress bar */}
        {!isComplete && (
          <Box w="100%" h="2px" bg="border.subtle" borderRadius="full" mb={4} overflow="hidden">
            <Box
              h="100%" bg="brand.500" borderRadius="full"
              w={`${progress}%`}
              transition="width 0.3s ease"
              position="relative"
            >
              <Box
                position="absolute" inset={0}
                bgGradient="linear(to-r, transparent, whiteAlpha.400, transparent)"
                bgSize="200% 100%"
                sx={{ animation: `${shimmer} 1.5s linear infinite` }}
              />
            </Box>
          </Box>
        )}

        {/* Text container — grows with content */}
        <Box
          p={6} border="1px solid" borderColor={isComplete ? 'brand.200' : 'border.muted'}
          borderRadius="xl" bg="surface" shadow="sm"
          transition="border-color 0.4s ease"
          position="relative"
          overflow="hidden"
        >
          {/* Shimmer line at top while writing */}
          {!isComplete && (
            <Box
              position="absolute" top={0} left={0} right={0} h="2px"
              bgGradient="linear(to-r, transparent, brand.400, transparent)"
              bgSize="200% 100%"
              sx={{ animation: `${shimmer} 2s linear infinite` }}
            />
          )}

          <Text fontSize="sm" whiteSpace="pre-wrap" lineHeight="1.8">
            {/* Revealed text */}
            <Text as="span" color="text.secondary">
              {displayedText.slice(0, revealedCount)}
            </Text>
            {/* Scrambled zone — slightly different style */}
            {!isComplete && (
              <Text as="span" color="brand.text" opacity={0.5} fontFamily="mono">
                {displayedText.slice(revealedCount)}
              </Text>
            )}
            {!isComplete && (
              <Box
                as="span" display="inline-block" w="2px" h="16px"
                bg="brand.500" ml="1px" verticalAlign="text-bottom"
                sx={{ animation: `${cursorBlink} 0.8s step-end infinite` }}
              />
            )}
          </Text>
        </Box>
      </Box>
    </Flex>
  );
}
