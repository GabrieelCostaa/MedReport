import { useEffect, useRef, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import Lenis from 'lenis';
import {
  Box,
  Button,
  Container,
  Flex,
  Heading,
  HStack,
  SimpleGrid,
  Text,
  VStack,
} from '@chakra-ui/react';
import { keyframes } from '@emotion/react';
import {
  motion,
  useInView,
  useScroll,
  useTransform,
} from 'framer-motion';

/* ─── Chakra + Motion ─── */
const MotionBox = motion(Box);
const MotionFlex = motion(Flex);

/* ─── config ─── */
const EASE = [0.65, 0.05, 0, 1] as const;
const DURATION = 0.75;
const SERIF = `'Playfair Display', Georgia, 'Times New Roman', serif`;

/* ─── colors ─── */
const C = {
  dark: '#0a0a0a',
  darkAlt: '#111111',
  accent: '#c8e64e',
  accentDark: '#a3c23a',
  accentMuted: '#8fa83a',
  white: '#f5f5f0',
  cream: '#e8e4d9',
  gray: '#888888',
  grayLight: '#aaaaaa',
  grayDark: '#333333',
};

/* ─── keyframes ─── */
const marqueeLeft = keyframes`
  0%   { transform: translateX(0); }
  100% { transform: translateX(-50%); }
`;

const drawPath = keyframes`
  0%   { stroke-dashoffset: 1000; }
  100% { stroke-dashoffset: 0; }
`;

const pulseGlow = keyframes`
  0%, 100% { opacity: 0.3; transform: scale(1); }
  50%      { opacity: 0.5; transform: scale(1.05); }
`;

const floatSlow = keyframes`
  0%   { transform: translate(0, 0) rotate(0deg); }
  33%  { transform: translate(30px, -20px) rotate(1deg); }
  66%  { transform: translate(-20px, 15px) rotate(-1deg); }
  100% { transform: translate(0, 0) rotate(0deg); }
`;

const floatSlowAlt = keyframes`
  0%   { transform: translate(0, 0) rotate(0deg); }
  33%  { transform: translate(-25px, 20px) rotate(-0.5deg); }
  66%  { transform: translate(15px, -25px) rotate(0.5deg); }
  100% { transform: translate(0, 0) rotate(0deg); }
`;

const meshMove = keyframes`
  0%   { background-position: 0% 50%; }
  50%  { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
`;

/* ─── Unsplash (free, no copyright) — full-bleed sizes ─── */
const IMG = {
  hero: 'https://images.unsplash.com/photo-1551190822-a9ce113d0459?auto=format&fit=crop&w=1920&q=85',
  surgeons: 'https://images.unsplash.com/photo-1579684385127-1ef15d508118?auto=format&fit=crop&w=1920&q=85',
  tablet: 'https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&w=1920&q=85',
  team: 'https://images.unsplash.com/photo-1666214280557-f1b5022eb634?auto=format&fit=crop&w=1920&q=85',
  doctor: 'https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?auto=format&fit=crop&w=1920&q=85',
  xray: 'https://images.unsplash.com/photo-1559757175-5700dde675bc?auto=format&fit=crop&w=1920&q=85',
  operating: 'https://images.unsplash.com/photo-1551076805-e1869033e561?auto=format&fit=crop&w=1920&q=85',
  corridor: 'https://images.unsplash.com/photo-1519494026892-80bbd2d6fd0d?auto=format&fit=crop&w=1920&q=85',
  microscope: 'https://images.unsplash.com/photo-1582719471384-894fbb16e074?auto=format&fit=crop&w=1920&q=85',
};

/* ─── Animated topographic SVG background ─── */
function TopoBg({ opacity = 0.08, color = C.accent }: { opacity?: number; color?: string }) {
  return (
    <Box position="absolute" inset={0} overflow="hidden" pointerEvents="none" opacity={opacity}>
      <Box position="absolute" inset="-20%" sx={{ animation: `${floatSlow} 25s ease-in-out infinite` }}>
        <svg width="100%" height="100%" viewBox="0 0 1200 900" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M0 450 Q150 300 300 420 Q450 540 600 380 Q750 220 900 350 Q1050 480 1200 320" stroke={color} strokeWidth="1" opacity="0.6" fill="none" />
          <path d="M0 500 Q200 350 400 470 Q600 590 800 430 Q1000 270 1200 370" stroke={color} strokeWidth="0.8" opacity="0.4" fill="none" />
          <path d="M0 380 Q100 250 250 340 Q400 430 550 300 Q700 170 850 280 Q1000 390 1200 250" stroke={color} strokeWidth="1.2" opacity="0.5" fill="none" />
          <ellipse cx="600" cy="450" rx="350" ry="200" stroke={color} strokeWidth="0.8" opacity="0.2" fill="none" />
          <ellipse cx="600" cy="450" rx="280" ry="160" stroke={color} strokeWidth="0.6" opacity="0.15" fill="none" />
        </svg>
      </Box>
      <Box position="absolute" inset="-15%" sx={{ animation: `${floatSlowAlt} 35s ease-in-out infinite` }}>
        <svg width="100%" height="100%" viewBox="0 0 1200 900" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M-100 600 Q100 450 300 550 Q500 650 700 500 Q900 350 1100 480 Q1300 610 1300 610" stroke={color} strokeWidth="0.7" opacity="0.35" fill="none" />
          <path d="M-50 300 Q150 180 350 280 Q550 380 750 250 Q950 120 1150 230 Q1250 290 1300 280" stroke={color} strokeWidth="0.9" opacity="0.25" fill="none" />
        </svg>
      </Box>
    </Box>
  );
}

/* ─── Caduceus SVG ─── */
function Caduceus({ size = 120, color = C.accent }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 120" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M30 35 Q15 20 25 10 Q35 0 50 10" stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round"
        strokeDasharray="1000" strokeDashoffset="0" style={{ animation: `${drawPath} 2s ease forwards` }} />
      <path d="M70 35 Q85 20 75 10 Q65 0 50 10" stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round"
        strokeDasharray="1000" strokeDashoffset="0" style={{ animation: `${drawPath} 2s ease 0.3s forwards` }} />
      <line x1="50" y1="15" x2="50" y2="115" stroke={color} strokeWidth="2"
        strokeDasharray="1000" strokeDashoffset="0" style={{ animation: `${drawPath} 1.5s ease 0.5s forwards` }} />
      <path d="M50 30 Q30 40 35 50 Q40 60 50 55 Q30 65 35 75 Q40 85 50 80 Q30 90 35 100 Q40 108 50 105"
        stroke={color} strokeWidth="1.8" fill="none" strokeLinecap="round"
        strokeDasharray="1000" strokeDashoffset="0" style={{ animation: `${drawPath} 2.5s ease 0.8s forwards` }} />
      <path d="M50 30 Q70 40 65 50 Q60 60 50 55 Q70 65 65 75 Q60 85 50 80 Q70 90 65 100 Q60 108 50 105"
        stroke={color} strokeWidth="1.8" fill="none" strokeLinecap="round"
        strokeDasharray="1000" strokeDashoffset="0" style={{ animation: `${drawPath} 2.5s ease 1s forwards` }} />
      <circle cx="50" cy="12" r="5" stroke={color} strokeWidth="1.5" fill="none"
        strokeDasharray="1000" strokeDashoffset="0" style={{ animation: `${drawPath} 1s ease 1.5s forwards` }} />
    </svg>
  );
}

/* ─── Logo icon ─── */
function LogoIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L12 6" /><path d="M12 18L12 22" />
      <path d="M9 6C9 4.34 10.34 3 12 3s3 1.34 3 3-1.34 3-3 3" />
      <path d="M15 6c0 1.66-1.34 3-3 3" />
      <path d="M9 9v4c0 1 .6 3 3 3s3-2 3-3V9" /><path d="M8 18h8" />
    </svg>
  );
}

function ArrowRight() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

/* ─── Roll Button (Lando Norris hover effect — text slides up on hover) ─── */
function RollButton({ children, icon, to = '/login', h = 56 }: {
  children: string; icon?: React.ReactNode; to?: string; h?: number;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <RouterLink to={to}
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      style={{
        display: 'inline-block', height: h, borderRadius: 12, overflow: 'hidden',
        background: C.accent, color: C.dark, textDecoration: 'none',
        fontWeight: 700, fontSize: h === 36 ? 14 : 16, padding: `0 ${h === 36 ? 20 : 32}px`,
        transition: 'transform 0.3s, box-shadow 0.3s',
        transform: hovered ? 'translateY(-2px)' : 'none',
        boxShadow: hovered ? `0 20px 40px ${C.accent}44` : 'none',
      }}>
      <div style={{
        display: 'flex', flexDirection: 'column',
        transition: 'transform 0.45s cubic-bezier(0.65, 0.05, 0, 1)',
        transform: hovered ? 'translateY(-50%)' : 'translateY(0)',
      }}>
        <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, height: h }}>{children}{icon}</span>
        <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, height: h }}>{children}{icon}</span>
      </div>
    </RouterLink>
  );
}

function RollOutlineButton({ children, href = '#sobre' }: {
  children: string; href?: string;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <a href={href}
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      style={{
        display: 'inline-block', height: 56, borderRadius: 12, overflow: 'hidden',
        background: 'transparent', color: hovered ? C.accent : 'white',
        border: `1px solid ${hovered ? C.accent : 'rgba(255,255,255,0.3)'}`,
        textDecoration: 'none', fontWeight: 500, fontSize: 16, padding: '0 32px',
        transition: 'transform 0.3s, color 0.3s, border-color 0.3s',
        transform: hovered ? 'translateY(-2px)' : 'none',
      }}>
      <div style={{
        display: 'flex', flexDirection: 'column',
        transition: 'transform 0.45s cubic-bezier(0.65, 0.05, 0, 1)',
        transform: hovered ? 'translateY(-50%)' : 'translateY(0)',
      }}>
        <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 56 }}>{children}</span>
        <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 56 }}>{children}</span>
      </div>
    </a>
  );
}

/* ─── Scroll-linked reveal ─── */
function Reveal({ children, delay = 0, y = 60 }: { children: React.ReactNode; delay?: number; y?: number }) {
  const ref = useRef(null);
  const isInView = useInView(ref, { margin: '-100px', once: false });
  return (
    <MotionBox ref={ref} initial={{ opacity: 0, y }}
      animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y }}
      transition={{ duration: DURATION, ease: EASE, delay }}>
      {children}
    </MotionBox>
  );
}

/* ─── Text clip reveal ─── */
function ClipReveal({ children, delay = 0 }: { children: React.ReactNode; delay?: number }) {
  const ref = useRef(null);
  const isInView = useInView(ref, { margin: '-60px', once: false });
  return (
    <Box ref={ref} overflow="hidden" pb="0.2em" mb="-0.2em">
      <MotionBox initial={{ y: '110%' }} animate={isInView ? { y: '0%' } : { y: '110%' }}
        transition={{ duration: 0.9, ease: EASE, delay }}>
        {children}
      </MotionBox>
    </Box>
  );
}

/* ─── Cinematic full-bleed section (SpaceX style) ─── */
function CinematicSection({ image, children, overlayOpacity = 0.55, minH = '100vh' }: {
  image: string; children: React.ReactNode; overlayOpacity?: number; minH?: string;
}) {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] });
  const imgScale = useTransform(scrollYProgress, [0, 1], [1.15, 1]);
  const imgY = useTransform(scrollYProgress, [0, 1], ['-5%', '5%']);

  return (
    <Box ref={ref} position="relative" minH={minH} overflow="hidden" bg={C.dark}
      data-nav-theme="dark" display="flex" alignItems="center" justifyContent="center">
      {/* Full-bleed parallax image */}
      <MotionBox position="absolute" inset="-10%" bgImage={`url(${image})`}
        bgSize="cover" bgPosition="center"
        style={{ scale: imgScale, y: imgY }} />
      {/* Dark gradient overlay for text readability */}
      <Box position="absolute" inset={0} bg={`rgba(0,0,0,${overlayOpacity})`} />
      <Box position="absolute" inset={0}
        bg={`linear-gradient(180deg, ${C.dark}88 0%, transparent 30%, transparent 60%, ${C.dark}cc 100%)`} />
      {/* Content */}
      <Box position="relative" zIndex={1} w="full" py={{ base: 16, md: 0 }}>
        {children}
      </Box>
    </Box>
  );
}

/* ─── Hover reveal card ─── */
function HoverRevealCard({ image, title, subtitle, label }: {
  image: string; title: string; subtitle: string; label: string;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <Box position="relative" overflow="hidden" borderRadius="2xl" cursor="pointer"
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      h={{ base: '320px', md: '420px' }} bg={C.darkAlt}>
      <MotionBox position="absolute" inset={0} bgImage={`url(${image})`} bgSize="cover" bgPosition="center"
        animate={{ scale: hovered ? 1.08 : 1, opacity: hovered ? 0.85 : 0.35 }}
        transition={{ duration: 0.6, ease: EASE }} />
      <Box position="absolute" inset={0}
        bg={`linear-gradient(180deg, transparent 20%, ${C.dark}ee 100%)`} />
      <Box position="absolute" top={4} left={4} zIndex={2}>
        <MotionBox px={3} py={1} borderRadius="md"
          bg={hovered ? C.accent : 'whiteAlpha.200'} transition={{ duration: 0.3 }}>
          <Text fontSize="2xs" fontWeight="700" color={hovered ? C.dark : 'white'}
            textTransform="uppercase" letterSpacing="0.1em">{label}</Text>
        </MotionBox>
      </Box>
      <VStack position="absolute" bottom={6} left={6} right={6} align="start" zIndex={2}>
        <MotionBox animate={{ y: hovered ? 0 : 10, opacity: hovered ? 1 : 0.7 }}
          transition={{ duration: 0.4, ease: EASE }}>
          <Heading fontFamily={SERIF} size="lg" color="white" fontWeight="700" lineHeight="1.2"
            letterSpacing="-0.02em">{title}</Heading>
          <Text fontSize="sm" color="whiteAlpha.600" mt={2} lineHeight="1.6">{subtitle}</Text>
        </MotionBox>
      </VStack>
    </Box>
  );
}

/* ─── Animated counter ─── */
function Counter({ end, suffix = '' }: { end: number; suffix?: string }) {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref as React.RefObject<Element>, { once: false, margin: '-50px' });

  useEffect(() => {
    if (!inView) { setCount(0); return; }
    const duration = 2000;
    const start = performance.now();
    const animate = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 4);
      setCount(Math.floor(eased * end));
      if (p < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }, [end, inView]);

  return (
    <Text ref={ref} fontFamily={SERIF} fontSize={{ base: '4xl', md: '6xl', lg: '7xl' }}
      fontWeight="900" color={C.accent} lineHeight="1" letterSpacing="-0.03em" whiteSpace="nowrap">
      {count.toLocaleString('pt-BR')}{suffix}
    </Text>
  );
}

/* ═══════════════════════════════════════════════
   SECTIONS
   ═══════════════════════════════════════════════ */

/* ─── NAVBAR ─── */

function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [navTheme, setNavTheme] = useState<'dark' | 'light'>('dark');

  useEffect(() => {
    const handler = () => {
      setScrolled(window.scrollY > 50);
      const sections = document.querySelectorAll('[data-nav-theme]');
      sections.forEach((section) => {
        const rect = section.getBoundingClientRect();
        if (rect.top <= 60 && rect.bottom > 60) {
          setNavTheme(section.getAttribute('data-nav-theme') as 'dark' | 'light' || 'dark');
        }
      });
    };
    window.addEventListener('scroll', handler, { passive: true });
    return () => window.removeEventListener('scroll', handler);
  }, []);

  const textColor = navTheme === 'dark' ? 'white' : C.dark;

  return (
    <MotionFlex
      as="nav" position="fixed" top={0} left={0} right={0} zIndex={100}
      py={scrolled ? 3 : 5} px={{ base: 4, md: 8 }}
      bg="transparent"
      backdropFilter={undefined}
      borderBottom="none"
      justify="center"
      initial={{ y: -80 }} animate={{ y: 0 }}
      transition={{ duration: 1, ease: EASE, delay: 0.5 }}
      style={{ transition: 'background 0.5s, padding 0.5s, border-color 0.5s' }}
    >
      <Container maxW="7xl">
        <Flex justify="space-between" align="center">
          <HStack gap={2.5}>
            <Box w="36px" h="36px" borderRadius="lg" bg={C.accent}
              display="flex" alignItems="center" justifyContent="center" color={C.dark}>
              <LogoIcon />
            </Box>
            <Box>
              <Text fontSize="md" fontWeight="800" color={textColor} letterSpacing="-0.02em"
                lineHeight="1" transition="color 0.5s">MedReport</Text>
              <Text fontSize="2xs" color={navTheme === 'dark' ? 'whiteAlpha.400' : C.gray}
                fontWeight="500" letterSpacing="0.08em" transition="color 0.5s">JUSTIFICATIVAS OPME</Text>
            </Box>
          </HStack>
          <HStack gap={3}>
            <Button as={RouterLink} to="/login" variant="ghost" size="sm"
              color={textColor} fontWeight="500"
              _hover={{ bg: navTheme === 'dark' ? 'whiteAlpha.100' : 'blackAlpha.50' }}>
              Entrar
            </Button>
            <RollButton to="/login" h={36}>Comecar gratis</RollButton>
          </HStack>
        </Flex>
      </Container>
    </MotionFlex>
  );
}

/* ─── HERO (full-bleed cinematic — SpaceX style) ─── */

function Hero() {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] });
  const heroY = useTransform(scrollYProgress, [0, 1], [0, 250]);
  const heroOpacity = useTransform(scrollYProgress, [0, 0.5], [1, 0]);
  const heroScale = useTransform(scrollYProgress, [0, 0.5], [1, 0.92]);
  const imgScale = useTransform(scrollYProgress, [0, 1], [1, 1.3]);
  const imgY = useTransform(scrollYProgress, [0, 1], ['0%', '15%']);

  return (
    <Box ref={ref} position="relative" h="100vh" overflow="hidden" bg={C.dark} data-nav-theme="dark">
      {/* Full-bleed hero image with parallax */}
      <MotionBox position="absolute" inset="-10%"
        bgImage={`url(${IMG.hero})`} bgSize="cover" bgPosition="center"
        style={{ scale: imgScale, y: imgY }} />

      {/* Heavy gradient overlay — dark at top/bottom, clear center */}
      <Box position="absolute" inset={0}
        bg={`linear-gradient(180deg, ${C.dark}dd 0%, ${C.dark}44 40%, ${C.dark}44 60%, ${C.dark}ee 100%)`} />

      {/* Topo lines */}
      <TopoBg opacity={0.06} color={C.accent} />

      {/* Glow orb */}
      <Box position="absolute" top="30%" right="15%" w="500px" h="500px" borderRadius="full"
        bg={C.accent} opacity={0.02} filter="blur(120px)"
        sx={{ animation: `${pulseGlow} 8s ease infinite` }} />

      {/* Caduceus watermark */}
      <Box position="absolute" right={{ base: '5%', lg: '8%' }} top="50%" transform="translateY(-50%)"
        opacity={0.03} display={{ base: 'none', lg: 'block' }}>
        <Caduceus size={500} color="#fff" />
      </Box>

      <Container maxW="7xl" position="relative" zIndex={1} h="full" display="flex" alignItems="center">
        <MotionBox style={{ y: heroY, opacity: heroOpacity, scale: heroScale }} w="full">
          <VStack gap={{ base: 6, md: 8 }} align="start" maxW="5xl">
            <MotionBox initial={{ opacity: 0, x: -30 }} animate={{ opacity: 1, x: 0 }}
              transition={{ duration: DURATION, delay: 0.4, ease: EASE }}>
              <HStack gap={3}>
                <Box w="40px" h="1px" bg={C.accent} />
                <Text fontSize="xs" fontWeight="600" color={C.accent} letterSpacing="0.2em" textTransform="uppercase">
                  Inteligencia Artificial para Medicina
                </Text>
              </HStack>
            </MotionBox>

            <Box>
              {[
                { delay: 0.5, content: <><Text as="span" color={C.accent}>Aprovando</Text><Text as="span" color="white"> laudos,</Text></> },
                { delay: 0.7, content: <Text as="span" color="white">protegendo</Text> },
                { delay: 0.9, content: <Text as="span" color="white">pacientes.</Text> },
              ].map((line, i) => (
                <Box key={i} overflow="hidden" pb="0.2em" mb="-0.2em">
                  <MotionBox
                    initial={{ y: '110%' }}
                    animate={{ y: '0%' }}
                    transition={{ duration: 0.9, ease: EASE, delay: line.delay }}
                  >
                    <Heading fontFamily={SERIF} fontSize={{ base: '3.5rem', md: '6rem', lg: '8rem' }}
                      fontWeight="900" lineHeight="0.95" letterSpacing="-0.03em">
                      {line.content}
                    </Heading>
                  </MotionBox>
                </Box>
              ))}
            </Box>

            <MotionBox initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: DURATION, delay: 1.1, ease: EASE }} maxW="xl">
              <Text fontSize={{ base: 'md', md: 'lg' }} color={C.grayLight} lineHeight="1.8" fontWeight="400">
                Pipeline de IA com 4 agentes. 74.000+ códigos TUSS. 96.000+ registros ANVISA.
                Referências PubMed verificáveis. De 45 minutos para 3.
              </Text>
            </MotionBox>

            <MotionBox initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: DURATION, delay: 1.3, ease: EASE }}>
              <HStack gap={4} flexWrap="wrap" mt={2}>
                <RollButton to="/login" icon={<ArrowRight />}>
                  Comecar agora
                </RollButton>
                <RollOutlineButton href="#sobre">
                  Saiba mais
                </RollOutlineButton>
              </HStack>
            </MotionBox>
          </VStack>
        </MotionBox>
      </Container>

      {/* Scroll indicator */}
      <MotionBox position="absolute" bottom={8} left="50%" ml="-1px"
        initial={{ opacity: 0 }} animate={{ opacity: 0.4 }} transition={{ delay: 2, duration: 1 }}>
        <Box w="2px" h="40px" bg={`linear-gradient(180deg, ${C.accent}, transparent)`} />
      </MotionBox>
    </Box>
  );
}

/* ─── MARQUEE ─── */

function Marquee() {
  const items = [
    '74.000+ códigos TUSS', '96.000+ registros ANVISA', '161 DUTs mapeadas',
    'Relatório em 3 min', 'RN 465/2021', 'PubMed em tempo real',
    'TISS/TUSS automático', 'CID-10 integrado', 'Conformidade LGPD',
  ];
  const doubled = [...items, ...items];

  return (
    <Box bg={C.dark} py={4} overflow="hidden" borderTop="1px solid" borderBottom="1px solid"
      borderColor="whiteAlpha.100" data-nav-theme="dark"
      sx={{
        maskImage: 'linear-gradient(90deg, transparent, white 10%, white 90%, transparent)',
        WebkitMaskImage: 'linear-gradient(90deg, transparent, white 10%, white 90%, transparent)',
      }}>
      <Box sx={{ animation: `${marqueeLeft} 45s linear infinite` }} display="flex" w="max-content">
        {doubled.map((item, i) => (
          <HStack key={i} gap={3} px={6} flexShrink={0}>
            <Box w="5px" h="5px" borderRadius="full" bg={C.accent} />
            <Text fontSize="xs" fontWeight="600" color="whiteAlpha.600" whiteSpace="nowrap"
              textTransform="uppercase" letterSpacing="0.1em">{item}</Text>
          </HStack>
        ))}
      </Box>
    </Box>
  );
}

/* ─── CINEMATIC STATEMENT (full-bleed image + giant serif text — SpaceX/Starlink style) ─── */

function Statement() {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] });
  const imgScale = useTransform(scrollYProgress, [0, 1], [1.2, 1]);
  const imgX = useTransform(scrollYProgress, [0, 1], ['-5%', '5%']);
  const textY = useTransform(scrollYProgress, [0.2, 0.8], [60, -60]);

  return (
    <Box ref={ref} position="relative" h="100vh" overflow="hidden" bg={C.dark}
      data-nav-theme="dark" id="sobre" display="flex" alignItems="center" justifyContent="center">
      {/* Full-bleed moving image */}
      <MotionBox position="absolute" inset="-15%"
        bgImage={`url(${IMG.operating})`} bgSize="cover" bgPosition="center"
        style={{ scale: imgScale, x: imgX }} />

      {/* Heavy overlay for text readability */}
      <Box position="absolute" inset={0} bg="rgba(0,0,0,0.6)" />
      <Box position="absolute" inset={0}
        bg={`linear-gradient(180deg, ${C.dark} 0%, transparent 25%, transparent 75%, ${C.dark} 100%)`} />

      <TopoBg opacity={0.04} color={C.accent} />

      <Container maxW="6xl" position="relative" zIndex={1}>
        <MotionBox style={{ y: textY }}>
          <VStack textAlign="center" gap={0}>
            <ClipReveal delay={0}>
              <Heading fontFamily={SERIF} fontSize={{ base: '2.8rem', md: '5rem', lg: '7rem' }}
                fontWeight="900" color="white" lineHeight="1.05" letterSpacing="-0.03em">
                <Text as="span" color={C.accent}>Eliminando</Text> glosas.
              </Heading>
            </ClipReveal>
            <ClipReveal delay={0.15}>
              <Heading fontFamily={SERIF} fontSize={{ base: '2.8rem', md: '5rem', lg: '7rem' }}
                fontWeight="900" color="white" lineHeight="1.05" letterSpacing="-0.03em">
                Defendendo <Text as="span" color={C.accent}>cirurgias.</Text>
              </Heading>
            </ClipReveal>
            <ClipReveal delay={0.3}>
              <Heading fontFamily={SERIF} fontSize={{ base: '2.8rem', md: '5rem', lg: '7rem' }}
                fontWeight="900" color="white" lineHeight="1.05" letterSpacing="-0.03em">
                Construindo
              </Heading>
            </ClipReveal>
            <ClipReveal delay={0.45}>
              <Heading fontFamily={SERIF} fontSize={{ base: '2.8rem', md: '5rem', lg: '7rem' }}
                fontWeight="900" lineHeight="1.05" letterSpacing="-0.03em">
                <Text as="span" color={C.accent}>evidencia</Text>
                <Text as="span" color="white"> clinica.</Text>
              </Heading>
            </ClipReveal>
          </VStack>
        </MotionBox>

        <Reveal delay={0.6}>
          <VStack mt={{ base: 10, md: 14 }} gap={4}>
            <Box w="48px" h="1px" bg={C.accent} />
            <Text fontSize={{ base: 'sm', md: 'md' }} color={C.grayLight} textAlign="center" maxW="lg" lineHeight="1.8">
              Cada justificativa cruza 74.000+ códigos TUSS, 96.000+ registros ANVISA,
              161 DUTs da ANS, referências PubMed e conformidade TISS. Automaticamente.
            </Text>
          </VStack>
        </Reveal>
      </Container>
    </Box>
  );
}

/* ─── STATS ─── */

function Stats() {
  const stats = [
    { value: 74000, suffix: '+', label: 'Códigos TUSS', sub: 'Base completa de materiais' },
    { value: 161, suffix: '', label: 'DUTs da ANS', sub: 'Critérios de elegibilidade' },
    { value: 96000, suffix: '+', label: 'Registros ANVISA', sub: 'Validação regulatória' },
    { value: 3, suffix: ' min', label: 'Por relatório', sub: 'Contra 45 min manual' },
  ];

  return (
    <Box
      py={{ base: 20, md: 32 }}
      position="relative"
      overflow="hidden"
      data-nav-theme="dark"
      bg={`linear-gradient(135deg, ${C.dark} 0%, #1a1a18 25%, #1c1e12 50%, #1a1a18 75%, ${C.dark} 100%)`}
      backgroundSize="400% 400%"
      animation={`${meshMove} 12s ease infinite`}
    >
      {/* Subtle accent glow orbs */}
      <Box
        position="absolute" top="-20%" left="-10%" w="50%" h="140%"
        bg={`radial-gradient(ellipse, ${C.accent}08 0%, transparent 70%)`}
        animation={`${floatSlow} 20s ease-in-out infinite`}
        pointerEvents="none"
      />
      <Box
        position="absolute" bottom="-20%" right="-10%" w="50%" h="140%"
        bg={`radial-gradient(ellipse, ${C.accent}06 0%, transparent 70%)`}
        animation={`${floatSlowAlt} 18s ease-in-out infinite`}
        pointerEvents="none"
      />
      <Container maxW="7xl" position="relative" zIndex={1}>
        <SimpleGrid columns={{ base: 2, md: 4 }} gap={{ base: 10, md: 8 }}>
          {stats.map((s, i) => (
            <Reveal key={i} delay={i * 0.1}>
              <VStack gap={2}>
                <Counter end={s.value} suffix={s.suffix} />
                <Text fontSize="sm" fontWeight="700" color="white" letterSpacing="-0.01em">{s.label}</Text>
                <Text fontSize="xs" color={C.grayLight} textAlign="center">{s.sub}</Text>
              </VStack>
            </Reveal>
          ))}
        </SimpleGrid>
      </Container>
    </Box>
  );
}

/* ─── CINEMATIC BREAK 1 (full-bleed, single phrase) ─── */

function CinematicBreak1() {
  return (
    <CinematicSection image={IMG.corridor} overlayOpacity={0.6}>
      <Container maxW="5xl">
        <VStack textAlign="center" gap={6}>
          <Reveal>
            <Caduceus size={80} color={C.accent} />
          </Reveal>
          <ClipReveal delay={0.1}>
            <Heading fontFamily={SERIF} fontSize={{ base: '2rem', md: '3.5rem', lg: '5rem' }}
              fontWeight="900" color="white" lineHeight="1.15" letterSpacing="-0.03em" maxW="4xl">
              "Se a justificativa nao segue a DUT,
              o <Text as="span" color={C.accent}>convenio nega.</Text>"
            </Heading>
          </ClipReveal>
          <Reveal delay={0.3}>
            <Text fontSize="sm" color={C.grayLight}>
              A realidade de quem trabalha com OPME no Brasil
            </Text>
          </Reveal>
        </VStack>
      </Container>
    </CinematicSection>
  );
}

/* ─── GALLERY ─── */

function Gallery() {
  return (
    <Box py={{ base: 16, md: 28 }} bg={C.dark} data-nav-theme="dark" position="relative" overflow="hidden">
      <TopoBg opacity={0.04} color={C.accent} />
      <Container maxW="7xl" position="relative" zIndex={1}>
        <Reveal>
          <HStack gap={3} mb={{ base: 8, md: 12 }}>
            <Box w="40px" h="1px" bg={C.accent} />
            <Text fontSize="xs" fontWeight="700" color={C.accent}
              textTransform="uppercase" letterSpacing="0.15em">
              Feito para o centro cirurgico
            </Text>
          </HStack>
        </Reveal>
        <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} gap={5}>
          <Reveal delay={0}>
            <HoverRevealCard image={IMG.surgeons} title="Pesquisador IA"
              subtitle="Busca automática de evidências no PubMed com DOI verificável" label="Camada 1" />
          </Reveal>
          <Reveal delay={0.1}>
            <HoverRevealCard image={IMG.tablet} title="Redator IA"
              subtitle="Gera a justificativa técnica completa seguindo padrão ANS" label="Camada 2" />
          </Reveal>
          <Reveal delay={0.2}>
            <HoverRevealCard image={IMG.team} title="Auditor e Validador"
              subtitle="Valida contra 74.000+ TUSS, 96.000+ ANVISA e 161 DUTs automaticamente" label="Camadas 3 e 4" />

          </Reveal>
        </SimpleGrid>
      </Container>
    </Box>
  );
}

/* ─── CINEMATIC BREAK 2 (full-bleed, microscope) ─── */

function CinematicBreak2() {
  return (
    <CinematicSection image={IMG.microscope} overlayOpacity={0.65} minH="80vh">
      <Container maxW="6xl">
        <Flex direction={{ base: 'column', lg: 'row' }} align="center" justify="space-between" gap={12}>
          <Box flex={1}>
            <ClipReveal>
              <Heading fontFamily={SERIF} fontSize={{ base: '2.5rem', md: '4rem', lg: '5.5rem' }}
                fontWeight="900" color="white" lineHeight="1.05" letterSpacing="-0.03em">
                De <Text as="span" color={C.accent}>45 minutos</Text>
              </Heading>
            </ClipReveal>
            <ClipReveal delay={0.15}>
              <Heading fontFamily={SERIF} fontSize={{ base: '2.5rem', md: '4rem', lg: '5.5rem' }}
                fontWeight="900" color="white" lineHeight="1.05" letterSpacing="-0.03em">
                para <Text as="span" color={C.accent}>3.</Text>
              </Heading>
            </ClipReveal>
          </Box>
          <Reveal delay={0.3}>
            <Text fontSize={{ base: 'md', md: 'lg' }} color={C.grayLight} maxW="md" lineHeight="1.8">
              Quatro agentes de IA trabalham em sequência para produzir uma justificativa
              técnica completa, com base legal, evidências PubMed e conformidade ANS.
              Tudo cruzado com 74.000+ TUSS, 96.000+ ANVISA e 161 DUTs de forma determinística.
            </Text>
          </Reveal>
        </Flex>
      </Container>
    </CinematicSection>
  );
}

/* ─── HORIZONTAL SCROLL FEATURES ─── */

const PIPELINE_FEATURES = [
  { num: '01', title: 'Pesquisador', desc: 'Busca evidências científicas no PubMed em tempo real. Encontra artigos com DOI verificável e nível de evidência classificado.', image: IMG.doctor },
  { num: '02', title: 'Redator', desc: 'Escreve a justificativa técnica completa seguindo o padrão ANS. Inclui base legal, falha terapêutica e risco de não realização.', image: IMG.xray },
  { num: '03', title: 'Auditor', desc: 'Revisa o texto, corrige inconsistências, verifica códigos TUSS e garante que todas as entidades técnicas estão presentes.', image: IMG.surgeons },
  { num: '04', title: 'Validador', desc: 'Checklist determinístico de 6 itens. Detecta off-label, contraindicações, conflitos de CID e diagnósticos vagos. Zero IA — pura lógica.', image: IMG.operating },
];

function HorizontalFeatures() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const rafId = useRef(0);
  const currentTx = useRef(0);
  const targetTx = useRef(0);

  useEffect(() => {
    const section = sectionRef.current;
    const track = trackRef.current;
    const bar = barRef.current;
    if (!section || !track || !bar) return;

    // Lerp loop — runs every frame, smoothly interpolates toward target
    const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
    const SMOOTH = 0.08; // lower = smoother/slower, higher = snappier

    let targetProg = 0;
    let currentProg = 0;

    const tick = () => {
      currentTx.current = lerp(currentTx.current, targetTx.current, SMOOTH);
      currentProg = lerp(currentProg, targetProg, SMOOTH);

      // Only update DOM if difference is noticeable (> 0.5px)
      track.style.transform = `translate3d(${currentTx.current}px, 0, 0)`;
      bar.style.transform = `scaleX(${currentProg})`;

      rafId.current = requestAnimationFrame(tick);
    };

    const onScroll = () => {
      const rect = section.getBoundingClientRect();
      const scrollable = section.offsetHeight - window.innerHeight;
      if (scrollable <= 0) return;

      // Start movement very early — when section is 80% below viewport
      const earlyStart = window.innerHeight * 0.8;
      const rawP = (earlyStart - rect.top) / (scrollable + earlyStart);
      const p = Math.max(0, Math.min(1, rawP));
      targetProg = p;

      // Start with first card well to the right, then shift left
      const startOffset = window.innerWidth * 0.5;
      const maxShift = track.scrollWidth - window.innerWidth + 96 + startOffset;
      targetTx.current = startOffset - p * maxShift;
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    onScroll();
    rafId.current = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      cancelAnimationFrame(rafId.current);
    };
  }, []);

  return (
    <div ref={sectionRef} data-nav-theme="light" style={{ height: '300vh', position: 'relative' }}>
      <div style={{
        position: 'sticky', top: 0, height: '100vh', overflow: 'hidden',
        background: C.white, display: 'flex', flexDirection: 'column', justifyContent: 'center',
      }}>
        <Container maxW="7xl" pt={16} pb={6}>
          <HStack gap={3} mb={4}>
            <Box w="40px" h="1px" bg={C.accent} />
            <Text fontSize="xs" fontWeight="700" color={C.accentMuted}
              textTransform="uppercase" letterSpacing="0.15em">Pipeline de 4 agentes</Text>
          </HStack>
          <Heading fontFamily={SERIF} fontSize={{ base: '2xl', md: '4xl' }} fontWeight="900"
            color={C.dark} letterSpacing="-0.03em" mb={6} maxW="2xl">
            Acompanhe cada etapa em tempo real
          </Heading>
        </Container>

        <div style={{ overflow: 'hidden', paddingLeft: '48px' }}>
          <div ref={trackRef} style={{
            display: 'flex', gap: '24px', paddingRight: '48px',
            willChange: 'transform',
          }}>
            {PIPELINE_FEATURES.map((f) => (
              <Box key={f.num} minW={{ base: '300px', md: '560px' }} flexShrink={0}>
                <Box borderRadius="2xl" overflow="hidden" bg={C.dark}
                  h={{ base: '300px', md: '380px' }} position="relative"
                  cursor="pointer"
                  _hover={{
                    '& > div:first-of-type': { opacity: 0.6, transform: 'scale(1.08)' },
                    '& > div:nth-of-type(2)': { opacity: 0.5 },
                  }}>
                  <Box position="absolute" inset={0} bgImage={`url(${f.image})`}
                    bgSize="cover" bgPosition="center" opacity={0.25}
                    transition="all 0.6s cubic-bezier(0.65, 0.05, 0, 1)" />
                  <Box position="absolute" inset={0} opacity={1}
                    bg={`linear-gradient(160deg, ${C.dark}cc 0%, ${C.dark}99 100%)`}
                    transition="opacity 0.6s cubic-bezier(0.65, 0.05, 0, 1)" />
                  <VStack position="relative" zIndex={1} p={{ base: 6, md: 8 }}
                    align="start" justify="end" h="full">
                    <Text fontFamily={SERIF} fontSize="7xl" fontWeight="900" color={C.accent}
                      lineHeight="1" letterSpacing="-0.05em" opacity={0.25}>{f.num}</Text>
                    <Heading fontFamily={SERIF} size="lg" color="white" fontWeight="700"
                      letterSpacing="-0.02em">{f.title}</Heading>
                    <Text fontSize="sm" color="whiteAlpha.600" lineHeight="1.7" maxW="md">{f.desc}</Text>
                  </VStack>
                </Box>
              </Box>
            ))}
          </div>
        </div>

        <Container maxW="7xl" mt={5}>
          <Box h="2px" bg="gray.200" borderRadius="full" overflow="hidden" maxW="200px">
            <div ref={barRef} style={{
              height: '100%', background: C.accent, borderRadius: '9999px',
              transformOrigin: 'left', willChange: 'transform',
            }} />
          </Box>
        </Container>
      </div>
    </div>
  );
}

/* ─── COMPLIANCE ─── */

function Compliance() {
  const specs = [
    'Ortopedia', 'Neurocirurgia', 'Cardiologia', 'Cirurgia Vascular',
    'Cirurgia Geral', 'Urologia', 'Ginecologia', 'Oftalmologia',
    'Otorrinolaringologia', 'Cirurgia Plastica',
  ];
  const items = [
    { code: 'RN 465/2021', label: 'Rol de Procedimentos', desc: '161 DUTs + 74.000+ TUSS + 96.000+ registros ANVISA' },
    { code: 'RN 452/2020', label: 'Padrao TISS', desc: 'Guias XML conforme padrao obrigatorio da ANS' },
    { code: 'Lei 13.709', label: 'LGPD', desc: 'Tratamento de dados sensiveis em conformidade' },
    { code: 'ANVISA', label: 'Registro de Produtos', desc: 'Validacao automatica do registro de cada OPME' },
  ];

  return (
    <Box pt={{ base: 20, md: 32 }} pb={{ base: 16, md: 20 }} bg={C.dark} data-nav-theme="dark" position="relative" overflow="hidden">
      <TopoBg opacity={0.05} color={C.accent} />
      {/* Caduceus — centered between both sub-sections */}
      <Box position="absolute" top="50%" right="-60px" transform="translateY(-50%)" opacity={0.03} pointerEvents="none">
        <Caduceus size={500} color="#fff" />
      </Box>

      {/* Compliance */}
      <Container maxW="7xl" position="relative" zIndex={1}>
        <Reveal>
          <HStack gap={3} mb={4}>
            <Box w="40px" h="1px" bg={C.accent} />
            <Text fontSize="xs" fontWeight="700" color={C.accent}
              textTransform="uppercase" letterSpacing="0.15em">Conformidade</Text>
          </HStack>
          <Heading fontFamily={SERIF} fontSize={{ base: '2xl', md: '4xl' }} fontWeight="900"
            color="white" letterSpacing="-0.03em" mb={{ base: 10, md: 14 }} maxW="2xl" lineHeight="1.1">
            Construido em cima da legislacao. Nao ao redor dela.
          </Heading>
        </Reveal>
        <SimpleGrid columns={{ base: 1, md: 2, lg: 4 }} gap={5}>
          {items.map((item, i) => (
            <Reveal key={i} delay={i * 0.1}>
              <Box p={6} bg="whiteAlpha.50" borderRadius="xl" border="1px solid" borderColor="whiteAlpha.100"
                h="full" _hover={{ bg: 'whiteAlpha.100', transform: 'translateY(-4px)', borderColor: `${C.accent}44` }}
                transition="all 0.4s cubic-bezier(0.65, 0.05, 0, 1)">
                <Box display="inline-block" px={3} py={1} mb={4} bg={C.accent} borderRadius="md"
                  fontSize="xs" fontWeight="700" color={C.dark} letterSpacing="0.03em">{item.code}</Box>
                <Heading size="sm" color="white" mb={2} fontWeight="700">{item.label}</Heading>
                <Text fontSize="sm" color="whiteAlpha.500" lineHeight="1.7">{item.desc}</Text>
              </Box>
            </Reveal>
          ))}
        </SimpleGrid>
      </Container>

      {/* Specialties */}
      <Container maxW="5xl" position="relative" zIndex={1} mt={{ base: 16, md: 24 }}>
        <Reveal>
          <VStack mb={10} textAlign="center">
            <HStack gap={3} mb={2}>
              <Box w="40px" h="1px" bg={C.accent} />
              <Text fontSize="xs" fontWeight="700" color={C.accent}
                textTransform="uppercase" letterSpacing="0.15em">Especialidades</Text>
              <Box w="40px" h="1px" bg={C.accent} />
            </HStack>
            <Heading fontFamily={SERIF} fontSize={{ base: '2xl', md: '3xl' }} fontWeight="900"
              color="white" letterSpacing="-0.03em">
              Feito para quem opera e prescreve OPME
            </Heading>
          </VStack>
        </Reveal>
        <Reveal delay={0.15}>
          <Flex flexWrap="wrap" justify="center" gap={3}>
            {specs.map((s) => (
              <Box key={s} px={6} py={3} borderRadius="full" border="1px solid"
                borderColor="whiteAlpha.200" fontSize="sm" fontWeight="500" color={C.grayLight}
                bg="whiteAlpha.50" cursor="default"
                _hover={{ borderColor: C.accent, color: "white", bg: `${C.accent}15`,
                  shadow: `0 4px 12px ${C.accent}22` }}
                transition="all 0.3s">{s}</Box>
            ))}
          </Flex>
        </Reveal>
      </Container>
    </Box>
  );
}

/* ─── TESTIMONIAL + FINAL CTA (sticky image, text scrolls over) ─── */

function Testimonial() {
  return (
    <Box position="relative" data-nav-theme="dark">
      {/* Sticky image that stays fixed, extends behind navbar */}
      <Box
        position="sticky"
        top={0}
        h="100vh"
        overflow="hidden"
        zIndex={0}
      >
        <Box position="absolute" inset={0} bgImage={`url(${IMG.team})`}
          bgSize="cover" bgPosition="center" />
        <Box position="absolute" inset={0} bg="rgba(0,0,0,0.65)" />
      </Box>

      {/* Text content that scrolls over the sticky image */}
      <Box position="relative" zIndex={1} mt="-100vh">
        {/* Testimonial */}
        <Flex minH="100vh" align="center" justify="center">
          <Container maxW="4xl">
            <Reveal>
              <VStack textAlign="center" gap={8}>
                <Box w="60px" h="1px" bg={C.accent} />
                <Heading fontFamily={SERIF} fontSize={{ base: 'xl', md: '2xl', lg: '3xl' }}
                  fontWeight="400" fontStyle="italic" color="white" lineHeight="1.7" maxW="3xl">
                  "Eu gastava 40 minutos por justificativa e ainda recebia negativa.
                  Com o MedReport, faco em 3 minutos e a taxa de aprovacao
                  subiu para praticamente 100%."
                </Heading>
                <VStack gap={1}>
                  <Text fontSize="sm" fontWeight="700" color="white">Dr. R. Oliveira</Text>
                  <Text fontSize="xs" color={C.grayLight}>Ortopedista — Sao Paulo, SP</Text>
                </VStack>
              </VStack>
            </Reveal>
          </Container>
        </Flex>

        {/* CTA + Footer — scrolls up naturally after testimonial */}
        <Flex minH="100vh" align="center" justify="center" direction="column">
          <Container maxW="4xl" flex={1} display="flex" alignItems="center">
            <Reveal>
              <VStack textAlign="center" gap={8} w="full">
                <ClipReveal>
                  <Heading fontFamily={SERIF} fontSize={{ base: '2.5rem', md: '4rem', lg: '5rem' }}
                    fontWeight="900" color="white" lineHeight="1.1" letterSpacing="-0.03em">
                    Pronto para <Text as="span" color={C.accent}>eliminar negativas</Text> da sua rotina?
                  </Heading>
                </ClipReveal>
                <Text fontSize={{ base: 'md', md: 'lg' }} color={C.grayLight} maxW="lg" lineHeight="1.7">
                  Junte-se aos médicos que já economizam horas por semana com justificativas
                  geradas por IA e validadas contra a legislação.
                </Text>
                <RollButton to="/login" icon={<ArrowRight />}>
                  Começar agora — é grátis
                </RollButton>
                <Text fontSize="xs" color="whiteAlpha.400">
                  Sem cartão de crédito. Primeiros 5 relatórios gratuitos.
                </Text>
              </VStack>
            </Reveal>
          </Container>

          {/* Footer inline */}
          <Container maxW="7xl" w="full" py={8}>
            <Flex justify="space-between" align={{ base: 'start', md: 'center' }}
              direction={{ base: 'column', md: 'row' }} gap={6}>
              <HStack gap={2.5}>
                <Box w="28px" h="28px" borderRadius="md" bg={C.accent}
                  display="flex" alignItems="center" justifyContent="center" color={C.dark}>
                  <LogoIcon size={14} />
                </Box>
                <Box>
                  <Text fontWeight="700" color="white" fontSize="sm">MedReport</Text>
                  <Text fontSize="2xs" color="whiteAlpha.400">Justificativas OPME inteligentes</Text>
                </Box>
              </HStack>
              <VStack align={{ base: 'start', md: 'end' }} gap={1}>
                <Text fontSize="xs" color="white">
                  ANS (RN 465) | TISS (RN 452) | LGPD (Lei 13.709) | ANVISA
                </Text>
                <Text fontSize="xs" color="whiteAlpha.700">
                  {new Date().getFullYear()} MedReport. Todos os direitos reservados.
                </Text>
              </VStack>
            </Flex>
          </Container>
        </Flex>
      </Box>
    </Box>
  );
}

function FinalCTA() { return null; }

/* ─── FOOTER ─── */

function Footer() { return null; }

/* ═══════════════════════════════════════════════
   PAGE
   ═══════════════════════════════════════════════ */

export default function Landing() {
  useEffect(() => {
    const lenis = new Lenis({
      duration: 1.2,
      easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      touchMultiplier: 2,
      infinite: false,
    });

    function raf(time: number) {
      lenis.raf(time);
      requestAnimationFrame(raf);
    }
    requestAnimationFrame(raf);

    return () => { lenis.destroy(); };
  }, []);

  return (
    <Box sx={{ overflowX: 'clip' }}>
      <Nav />
      <Hero />
      <Marquee />
      <Statement />
      <Stats />
      <CinematicBreak1 />
      <Gallery />
      <CinematicBreak2 />
      <HorizontalFeatures />
      <Compliance />
      <Testimonial />
      <FinalCTA />
      <Footer />
    </Box>
  );
}
