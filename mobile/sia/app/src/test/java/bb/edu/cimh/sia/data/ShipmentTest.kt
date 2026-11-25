package bb.edu.cimh.sia.data

import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

class ShipmentTest {
    private fun line(id: String, source: String?) =
        RequestLine(lineId = id, productId = "P$id", product = ProductSnapshot(name = id), qty = 1, source = source)

    @Test fun onlyUnshippedCimhLinesShipFromThePhone() {
        val r = OrderRequest(
            id = "ORD1", type = "PAID", status = "PURCHASING", version = 3,
            lines = listOf(line("L1", "CIMH"), line("L2", "SUPPLIER"), line("L3", "CIMH")),
            shipments = listOf(Shipment(id = "SHP1", source = "CIMH", lineIds = listOf("L1"))),
        )
        assertEquals(listOf("L3"), r.cimhToShip.map { it.lineId })
    }

    @Test fun bodyNamesTheSourceAndLinesAndDropsEmptyTracking() {
        val body = ApiJson.encodeToJsonElement(
            ShipmentInput.serializer(),
            ShipmentInput(lineIds = listOf("L3"), carrier = "HAND", cost = "0.00", date = "2026-11-19"),
        ).jsonObject
        assertEquals("CIMH", body["source"]!!.jsonPrimitive.content)
        assertEquals("L3", body["lineIds"]!!.jsonArray.single().jsonPrimitive.content)
        assertFalse("tracking" in body) // explicitNulls = false: the server reads a missing value as none
        assertEquals("0.00", body["cost"]!!.jsonPrimitive.content) // required since 2026-11-24
    }

    @Test fun shippingCostIsTheApiMoneyString() {
        assertEquals("45.00", shippingCost("45"))
        assertEquals("45.50", shippingCost(" 45.5 "))
        assertEquals("0.00", shippingCost("0.00"))
        assertNull(shippingCost(""))
        assertNull(shippingCost("4,50"))
        assertNull(shippingCost("45.555"))
        assertNull(shippingCost("-1"))
    }
}
