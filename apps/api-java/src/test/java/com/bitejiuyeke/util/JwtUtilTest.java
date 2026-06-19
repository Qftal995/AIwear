package com.bitejiuyeke.util;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.security.Keys;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.test.util.ReflectionTestUtils;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class JwtUtilTest {

    @Mock
    private StringRedisTemplate redisTemplate;

    @Mock
    private ValueOperations<String, String> valueOperations;

    @InjectMocks
    private JwtUtil jwtUtil;

    private static final String TEST_SECRET = "this-is-a-test-secret-key-for-jwt-signing-256bit";
    private static final SecretKey KEY = Keys.hmacShaKeyFor(TEST_SECRET.getBytes(StandardCharsets.UTF_8));

    @BeforeEach
    void setUp() {
        ReflectionTestUtils.setField(jwtUtil, "secret", TEST_SECRET);
        ReflectionTestUtils.setField(jwtUtil, "expiration", 24L);
        lenient().when(redisTemplate.opsForValue()).thenReturn(valueOperations);
    }

    @Test
    void parseToken_withValidHeader_shouldExtractToken() {
        String token = jwtUtil.parseToken("Bearer abc.def.ghi");
        assertEquals("abc.def.ghi", token);
    }

    @Test
    void parseToken_withNullHeader_shouldThrowException() {
        assertThrows(RuntimeException.class, () -> jwtUtil.parseToken(null));
    }

    @Test
    void parseToken_withBlankHeader_shouldThrowException() {
        assertThrows(RuntimeException.class, () -> jwtUtil.parseToken("   "));
    }

    @Test
    void getUserId_withValidToken_shouldReturnUserId() {
        Map<String, Object> claims = new HashMap<>();
        claims.put("userId", 42L);
        claims.put("username", "testuser");

        String token = Jwts.builder()
                .setClaims(claims)
                .setIssuedAt(new Date())
                .setExpiration(new Date(System.currentTimeMillis() + 3600000))
                .signWith(KEY, SignatureAlgorithm.HS256)
                .compact();

        Long userId = jwtUtil.getUserId(token);
        assertEquals(42L, userId);
    }

    @Test
    void getUserId_withInvalidToken_shouldThrowException() {
        assertThrows(Exception.class, () -> jwtUtil.getUserId("invalid.token.here"));
    }

    @Test
    void removeToken_withBlankToken_shouldReturnTrue() {
        assertTrue(jwtUtil.removeToken(null));
        assertTrue(jwtUtil.removeToken("  "));
    }
}
