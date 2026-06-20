package com.runeclaw;

import java.awt.Rectangle;
import java.util.List;
import java.util.Map;

/**
 * Snapshot of live GE context for the companion actuator (handoff §2.6).
 * Serialized to snake_case JSON via Gson's LOWER_CASE_WITH_UNDERSCORES policy,
 * so e.g. {@code geOpen} -> {@code ge_open}, {@code itemId} -> {@code item_id}.
 */
class GeState
{
	boolean geOpen;
	boolean collectionOpen;
	Integer freeSlot;
	List<OfferState> offers;
	Map<String, Bounds> widgets;
	Bounds clientBounds;

	static class OfferState
	{
		final int slot;
		final String state;
		final int itemId;
		final int price;
		final int qty;

		OfferState(int slot, String state, int itemId, int price, int qty)
		{
			this.slot = slot;
			this.state = state;
			this.itemId = itemId;
			this.price = price;
			this.qty = qty;
		}
	}

	static class Bounds
	{
		final int x;
		final int y;
		final int w;
		final int h;

		Bounds(int x, int y, int w, int h)
		{
			this.x = x;
			this.y = y;
			this.w = w;
			this.h = h;
		}

		static Bounds of(Rectangle r)
		{
			return new Bounds(r.x, r.y, r.width, r.height);
		}
	}
}
