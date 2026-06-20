package com.runeclaw;

import net.runelite.client.config.Config;
import net.runelite.client.config.ConfigGroup;
import net.runelite.client.config.ConfigItem;

@ConfigGroup(RuneClawConfig.GROUP)
public interface RuneClawConfig extends Config
{
	String GROUP = "runeclaw";

	@ConfigItem(
		keyName = "geStateServerEnabled",
		name = "Enable /ge-state server",
		description = "Serve live GE state + widget bounds on a loopback HTTP port for the companion actuator."
	)
	default boolean geStateServerEnabled()
	{
		return true;
	}

	@ConfigItem(
		keyName = "geStatePort",
		name = "GE-state port",
		description = "Loopback port for the /ge-state HTTP server (must match companion config plugin_ge_state_port)."
	)
	default int geStatePort()
	{
		return 8766;
	}
}
