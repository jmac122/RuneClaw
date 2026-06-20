package com.runeclaw;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import lombok.extern.slf4j.Slf4j;

/**
 * Tiny embedded HTTP server exposing {@code GET /ge-state} on loopback only (handoff §2.6).
 *
 * <p>Requests are served from {@link GeStateService#currentJson()} — a cached snapshot — so
 * the server thread never touches the game API. Bound to 127.0.0.1 exclusively.
 */
@Slf4j
class GeStateServer
{
	private final GeStateService service;
	private HttpServer server;

	GeStateServer(GeStateService service)
	{
		this.service = service;
	}

	void start(int port) throws IOException
	{
		HttpServer httpServer = HttpServer.create(
			new InetSocketAddress(InetAddress.getByName("127.0.0.1"), port), 0);
		httpServer.createContext("/ge-state", exchange ->
		{
			byte[] body = service.currentJson().getBytes(StandardCharsets.UTF_8);
			exchange.getResponseHeaders().set("Content-Type", "application/json");
			exchange.sendResponseHeaders(200, body.length);
			try (OutputStream os = exchange.getResponseBody())
			{
				os.write(body);
			}
		});
		httpServer.setExecutor(null);
		httpServer.start();
		server = httpServer;
		log.info("RuneClaw /ge-state serving on http://127.0.0.1:{}/ge-state", port);
	}

	void stop()
	{
		if (server != null)
		{
			server.stop(0);
			server = null;
		}
	}
}
