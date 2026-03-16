import { useState, useEffect, useRef } from 'react';
import { Box, Text } from '@chakra-ui/react';
import { cursorBlink } from '../animations';

interface TypewriterLineProps {
  text: string;
  onComplete?: () => void;
  variant?: 'terminal' | 'default';
}

export default function TypewriterLine({ text, onComplete, variant = 'terminal' }: TypewriterLineProps) {
  const [displayed, setDisplayed] = useState('');
  const completeRef = useRef(false);

  useEffect(() => {
    setDisplayed('');
    completeRef.current = false;
    let i = 0;
    const timer = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(timer);
        if (!completeRef.current) {
          completeRef.current = true;
          onComplete?.();
        }
      }
    }, 22);
    return () => clearInterval(timer);
  }, [text, onComplete]);

  const isTerminal = variant === 'terminal';

  return (
    <Text
      fontSize={isTerminal ? 'xs' : 'sm'}
      color={isTerminal ? 'green.300' : 'gray.600'}
      fontFamily={isTerminal ? 'mono' : undefined}
      lineHeight="tall"
      display="inline"
    >
      {displayed}
      <Box
        as="span" display="inline-block" w="1.5px" h={isTerminal ? '12px' : '14px'}
        bg={isTerminal ? 'green.400' : 'blue.500'} ml="1px"
        verticalAlign="text-bottom"
        sx={{ animation: `${cursorBlink} 0.8s step-end infinite` }}
      />
    </Text>
  );
}
