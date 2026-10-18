package cn.superjlu.app;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = {28, 35})
public class SchoolHttpTest {
    static class Connection extends HttpURLConnection {
        final ByteArrayOutputStream sent = new ByteArrayOutputStream();
        boolean closed, failed;
        int code = 200;
        Connection() throws Exception { super(new URL("https://iedu.jlu.edu.cn/synthetic")); }
        @Override public void disconnect() { closed = true; }
        @Override public boolean usingProxy() { return false; }
        @Override public void connect() {}
        @Override public int getResponseCode() throws java.io.IOException {
            if (failed) throw new java.io.IOException("offline");
            return code;
        }
        @Override public InputStream getInputStream() { return new ByteArrayInputStream(new byte[]{1,2,3}); }
        @Override public InputStream getErrorStream() { return new ByteArrayInputStream(new byte[]{4,5}); }
        @Override public OutputStream getOutputStream() { return sent; }
        @Override public Map<String,List<String>> getHeaderFields() {
            Map<String,List<String>> result = new LinkedHashMap<>();
            result.put(null, Arrays.asList("HTTP/1.1 200 OK"));
            result.put("Set-Cookie", Arrays.asList("A=test; Path=/", "B=test; Path=/"));
            result.put("Location", Arrays.asList("/next"));
            return result;
        }
    }

    @Test public void singleHopPreservesStatusCookiesBodyAndTimeouts() throws Exception {
        Connection connection = new Connection();
        connection.code = 302;
        SchoolHttp.Result result = SchoolHttp.exchange(connection, "GET", "{\"Cookie\":\"A=test\"}", new byte[0], 4000);
        assertEquals(302, result.code);
        assertFalse(connection.getInstanceFollowRedirects());
        assertEquals(4000, connection.getConnectTimeout());
        assertEquals(4000, connection.getReadTimeout());
        assertEquals("A=test", connection.getRequestProperty("Cookie"));
        assertTrue(result.headers.contains("Set-Cookie: A=test"));
        assertTrue(result.headers.contains("Set-Cookie: B=test"));
        assertArrayEquals(new byte[]{1,2,3}, result.body);
        assertTrue(connection.closed);
    }

    @Test public void postBodyIsSentExactlyOnceAndErrorBodyIsPreserved() throws Exception {
        Connection connection = new Connection();
        connection.code = 403;
        byte[] data = new byte[]{7,8,9};
        SchoolHttp.Result result = SchoolHttp.exchange(connection, "POST", "{}", data, 4000);
        assertArrayEquals(data, connection.sent.toByteArray());
        assertArrayEquals(new byte[]{4,5}, result.body);
        assertEquals(403, result.code);
    }

    @Test public void failedRequestDisconnectsAndDoesNotRetryPost() throws Exception {
        Connection connection = new Connection();
        connection.failed = true;
        try {
            SchoolHttp.exchange(connection, "POST", "{}", new byte[]{7}, 4000);
            fail("expected failure");
        } catch (java.io.IOException expected) {
            assertTrue(connection.closed);
            assertArrayEquals(new byte[]{7}, connection.sent.toByteArray());
        }
    }

    @Test public void cleartextTargetIsRejected() throws Exception {
        try { SchoolHttp.request("http://iedu.jlu.edu.cn/", "GET", "{}", new byte[0], 4000); fail(); }
        catch (IllegalArgumentException expected) { assertTrue(expected.getMessage().contains("HTTPS")); }
    }
}
