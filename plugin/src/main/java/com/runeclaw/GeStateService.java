package com.runeclaw;

import com.google.gson.FieldNamingPolicy;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.awt.Rectangle;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.inject.Inject;
import javax.inject.Singleton;
import net.runelite.api.Client;
import net.runelite.api.GrandExchangeOffer;
import net.runelite.api.GrandExchangeOfferState;
import net.runelite.api.gameval.InterfaceID;
import net.runelite.api.widgets.ComponentID;
import net.runelite.api.widgets.Widget;

/**
 * Builds the {@link GeState} snapshot from live client state and caches it as JSON.
 *
 * <p>{@link #refresh()} reads {@link Client} and MUST run on the client thread; the HTTP
 * server only ever reads {@link #currentJson()} (a volatile string), so it never touches
 * the game API off-thread. Widget ids are the version-exact gameval constants for the GE
 * offers interface.
 */
@Singleton
class GeStateService
{
	private static final Gson GSON = new GsonBuilder()
		.setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
		.create();

	private static final int GE_GROUP_ID = InterfaceID.GeOffers.UNIVERSE >>> 16;

	/** /ge-state widget key -> RuneLite component id (handoff §2.6). */
	private static final Map<String, Integer> WIDGET_IDS = new LinkedHashMap<>();

	static
	{
		WIDGET_IDS.put("ge_window", InterfaceID.GeOffers.UNIVERSE);
		WIDGET_IDS.put("offer_setup", InterfaceID.GeOffers.SETUP);
		WIDGET_IDS.put("confirm_button", InterfaceID.GeOffers.SETUP_CONFIRM);
		WIDGET_IDS.put("collect_box", InterfaceID.GeOffers.COLLECTALL);
		WIDGET_IDS.put("back_button", InterfaceID.GeOffers.BACK);
		WIDGET_IDS.put("chatbox_input", ComponentID.CHATBOX_FULL_INPUT);
		WIDGET_IDS.put("ge_slot_0", InterfaceID.GeOffers.INDEX_0);
		WIDGET_IDS.put("ge_slot_1", InterfaceID.GeOffers.INDEX_1);
		WIDGET_IDS.put("ge_slot_2", InterfaceID.GeOffers.INDEX_2);
		WIDGET_IDS.put("ge_slot_3", InterfaceID.GeOffers.INDEX_3);
		WIDGET_IDS.put("ge_slot_4", InterfaceID.GeOffers.INDEX_4);
		WIDGET_IDS.put("ge_slot_5", InterfaceID.GeOffers.INDEX_5);
		WIDGET_IDS.put("ge_slot_6", InterfaceID.GeOffers.INDEX_6);
		WIDGET_IDS.put("ge_slot_7", InterfaceID.GeOffers.INDEX_7);
	}

	private final Client client;
	private volatile String cachedJson = "{\"ge_open\":false}";

	@Inject
	GeStateService(Client client)
	{
		this.client = client;
	}

	int geGroupId()
	{
		return GE_GROUP_ID;
	}

	String currentJson()
	{
		return cachedJson;
	}

	/** Rebuild the cached snapshot. Must be called on the client thread. */
	void refresh()
	{
		GeState state = new GeState();
		state.clientBounds = new GeState.Bounds(0, 0, client.getCanvasWidth(), client.getCanvasHeight());

		Widget root = client.getWidget(InterfaceID.GeOffers.UNIVERSE);
		state.geOpen = root != null && !root.isHidden();
		state.collectionOpen = false; // TODO confirm GeCollect interface during live testing

		GrandExchangeOffer[] offers = client.getGrandExchangeOffers();
		state.offers = activeOffers(offers);
		state.freeSlot = firstEmptySlot(offers);
		state.widgets = state.geOpen ? buildWidgets() : new LinkedHashMap<>();

		cachedJson = GSON.toJson(state);
	}

	private List<GeState.OfferState> activeOffers(GrandExchangeOffer[] offers)
	{
		List<GeState.OfferState> out = new ArrayList<>();
		if (offers == null)
		{
			return out;
		}
		for (int slot = 0; slot < offers.length; slot++)
		{
			GrandExchangeOffer o = offers[slot];
			if (o == null || o.getState() == GrandExchangeOfferState.EMPTY)
			{
				continue;
			}
			out.add(new GeState.OfferState(
				slot, o.getState().name(), o.getItemId(), o.getPrice(), o.getTotalQuantity()));
		}
		return out;
	}

	private Integer firstEmptySlot(GrandExchangeOffer[] offers)
	{
		if (offers == null)
		{
			return null;
		}
		for (int slot = 0; slot < offers.length; slot++)
		{
			GrandExchangeOffer o = offers[slot];
			if (o == null || o.getState() == GrandExchangeOfferState.EMPTY)
			{
				return slot;
			}
		}
		return null;
	}

	private Map<String, GeState.Bounds> buildWidgets()
	{
		Map<String, GeState.Bounds> map = new LinkedHashMap<>();
		for (Map.Entry<String, Integer> e : WIDGET_IDS.entrySet())
		{
			Widget w = client.getWidget(e.getValue());
			if (w == null || w.isHidden())
			{
				continue;
			}
			Rectangle b = w.getBounds();
			if (b != null)
			{
				map.put(e.getKey(), GeState.Bounds.of(b));
			}
		}
		return map;
	}
}
