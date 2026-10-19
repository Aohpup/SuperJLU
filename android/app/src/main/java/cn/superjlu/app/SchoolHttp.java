package cn.superjlu.app;

import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

/** Single HTTPS hop using Android's verified TLS stack; Python owns cookies/redirects. */
public final class SchoolHttp {
    public static final class Result {
        public final int code;
        public final String headers;
        public final byte[] body;
        Result(int code, String headers, byte[] body) {
            this.code = code; this.headers = headers; this.body = body;
        }
    }

    public static Result request(String url, String method, String headerJson, byte[] body, int timeout) throws Exception {
        URL target = new URL(url);
        if (!"https".equals(target.getProtocol())) throw new IllegalArgumentException("HTTPS required");
        HttpURLConnection connection = (HttpURLConnection) target.openConnection();
        return exchange(connection, method, headerJson, body, timeout);
    }

    static Result exchange(HttpURLConnection connection, String method, String headerJson, byte[] body, int timeout) throws Exception {
        connection.setInstanceFollowRedirects(false);
        connection.setUseCaches(false);
        connection.setConnectTimeout(timeout);
        connection.setReadTimeout(timeout);
        connection.setRequestMethod(method);
        try {
            JSONObject headers = new JSONObject(headerJson);
            for (Iterator<String> keys = headers.keys(); keys.hasNext();) {
                String key = keys.next();
                connection.setRequestProperty(key, headers.getString(key));
            }
            if (body.length > 0) {
                connection.setDoOutput(true);
                connection.setFixedLengthStreamingMode(body.length);
                try (java.io.OutputStream output = connection.getOutputStream()) { output.write(body); }
            }
            int code = connection.getResponseCode();
            StringBuilder raw = new StringBuilder();
            for (Map.Entry<String, List<String>> entry : connection.getHeaderFields().entrySet()) {
                if (entry.getKey() != null) for (String value : entry.getValue()) {
                    raw.append(entry.getKey()).append(": ").append(value).append("\r\n");
                }
            }
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            InputStream stream = code >= 400 ? connection.getErrorStream() : connection.getInputStream();
            long deadline = android.os.SystemClock.elapsedRealtime() + timeout;
            if (stream != null) try (InputStream input = stream) {
                byte[] buffer = new byte[65536];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    bytes.write(buffer, 0, count);
                    if (bytes.size() > 24 * 1024 * 1024) throw new java.io.IOException("HTTPS response too large");
                    if (android.os.SystemClock.elapsedRealtime() > deadline) throw new java.net.SocketTimeoutException();
                }
            }
            return new Result(code, raw.toString(), bytes.toByteArray());
        } finally { connection.disconnect(); }
    }
}
