package com.runeclaw;

import com.google.inject.Provides;
import javax.inject.Inject;
import lombok.extern.slf4j.Slf4j;
import net.runelite.api.events.GameTick;
import net.runelite.api.events.GrandExchangeOfferChanged;
import net.runelite.api.events.WidgetClosed;
import net.runelite.api.events.WidgetLoaded;
import net.runelite.client.callback.ClientThread;
import net.runelite.client.config.ConfigManager;
import net.runelite.client.eventbus.Subscribe;
import net.runelite.client.plugins.Plugin;
import net.runelite.client.plugins.PluginDescriptor;

@Slf4j
@PluginDescriptor(
	name = "RuneClaw",
	description = "GE flip assistant: exposes live GE state + widget bounds to the RuneClaw companion.",
	tags = {"grand", "exchange", "ge", "flip", "flipping", "money"}
)
public class RuneClawPlugin extends Plugin
{
	private static final int REFRESH_EVERY_TICKS = 2;

	@Inject
	private ClientThread clientThread;

	@Inject
	private RuneClawConfig config;

	@Inject
	private GeStateService geStateService;

	private GeStateServer server;
	private int tickCounter;

	@Override
	protected void startUp() throws Exception
	{
		if (config.geStateServerEnabled())
		{
			server = new GeStateServer(geStateService);
			server.start(config.geStatePort());
			clientThread.invoke(geStateService::refresh);
		}
		log.info("RuneClaw started");
	}

	@Override
	protected void shutDown()
	{
		if (server != null)
		{
			server.stop();
			server = null;
		}
		log.info("RuneClaw stopped");
	}

	@Subscribe
	public void onGameTick(GameTick tick)
	{
		if (server != null && ++tickCounter % REFRESH_EVERY_TICKS == 0)
		{
			geStateService.refresh();
		}
	}

	@Subscribe
	public void onGrandExchangeOfferChanged(GrandExchangeOfferChanged event)
	{
		if (server != null)
		{
			geStateService.refresh();
		}
	}

	@Subscribe
	public void onWidgetLoaded(WidgetLoaded event)
	{
		if (server != null && event.getGroupId() == geStateService.geGroupId())
		{
			geStateService.refresh();
		}
	}

	@Subscribe
	public void onWidgetClosed(WidgetClosed event)
	{
		if (server != null && event.getGroupId() == geStateService.geGroupId())
		{
			geStateService.refresh();
		}
	}

	@Provides
	RuneClawConfig provideConfig(ConfigManager configManager)
	{
		return configManager.getConfig(RuneClawConfig.class);
	}
}
