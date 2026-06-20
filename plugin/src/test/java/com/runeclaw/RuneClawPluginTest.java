package com.runeclaw;

import net.runelite.client.RuneLite;
import net.runelite.client.externalplugins.ExternalPluginManager;

/**
 * Dev launcher: runs the RuneLite client with this plugin side-loaded.
 * Use `./gradlew run` to start RuneLite in developer mode for live testing.
 */
public class RuneClawPluginTest
{
	public static void main(String[] args) throws Exception
	{
		ExternalPluginManager.loadBuiltin(RuneClawPlugin.class);
		RuneLite.main(args);
	}
}
