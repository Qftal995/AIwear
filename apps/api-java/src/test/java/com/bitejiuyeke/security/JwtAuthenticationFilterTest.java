package com.bitejiuyeke.security;

import com.bitejiuyeke.util.JwtUtil;
import jakarta.servlet.FilterChain;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.io.PrintWriter;
import java.io.StringWriter;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class JwtAuthenticationFilterTest {

    @Mock
    private JwtUtil jwtUtil;

    @Mock
    private HttpServletRequest request;

    @Mock
    private HttpServletResponse response;

    @Mock
    private FilterChain chain;

    @InjectMocks
    private JwtAuthenticationFilter filter;

    private StringWriter responseWriter;

    private void stubResponseWriter() throws Exception {
        responseWriter = new StringWriter();
        PrintWriter pw = new PrintWriter(responseWriter);
        lenient().when(response.getWriter()).thenReturn(pw);
    }

    @Test
    void shouldNotFilter_publicPaths_shouldReturnTrue() {
        when(request.getServletPath()).thenReturn("/api/health");
        assertTrue(filter.shouldNotFilter(request));
    }

    @Test
    void shouldNotFilter_userSendCode_shouldReturnTrue() {
        when(request.getServletPath()).thenReturn("/api/user/send-code");
        assertTrue(filter.shouldNotFilter(request));
    }

    @Test
    void shouldNotFilter_userAuth_shouldReturnTrue() {
        when(request.getServletPath()).thenReturn("/api/user/auth");
        assertTrue(filter.shouldNotFilter(request));
    }

    @Test
    void shouldNotFilter_protectedApi_shouldReturnFalse() {
        when(request.getServletPath()).thenReturn("/api/agent/chat");
        assertFalse(filter.shouldNotFilter(request));
    }

    @Test
    void doFilterInternal_missingAuthHeader_shouldReturn401() throws Exception {
        stubResponseWriter();
        when(request.getHeader("Authorization")).thenReturn(null);

        filter.doFilterInternal(request, response, chain);

        verify(response).setStatus(401);
    }

    @Test
    void doFilterInternal_blankAuthHeader_shouldReturn401() throws Exception {
        stubResponseWriter();
        when(request.getHeader("Authorization")).thenReturn("   ");

        filter.doFilterInternal(request, response, chain);

        verify(response).setStatus(401);
    }

    @Test
    void doFilterInternal_validToken_shouldSetUserId() throws Exception {
        stubResponseWriter();
        when(request.getHeader("Authorization")).thenReturn("Bearer valid-token");
        when(jwtUtil.parseToken("Bearer valid-token")).thenReturn("valid-token");
        when(jwtUtil.getUserId("valid-token")).thenReturn(42L);

        filter.doFilterInternal(request, response, chain);

        verify(request).setAttribute("userId", 42L);
        verify(chain).doFilter(request, response);
    }

    @Test
    void doFilterInternal_invalidToken_shouldReturn401() throws Exception {
        stubResponseWriter();
        when(request.getHeader("Authorization")).thenReturn("Bearer bad-token");
        when(jwtUtil.parseToken("Bearer bad-token")).thenReturn("bad-token");
        when(jwtUtil.getUserId("bad-token")).thenThrow(new RuntimeException("无效令牌"));

        filter.doFilterInternal(request, response, chain);

        verify(response).setStatus(401);
        verify(chain, never()).doFilter(any(), any());
    }
}
