package bb.edu.cimh.sia.data

import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
            ShipmentInput(lineIds = listOf("L3"), carrier = "HAND", date = "2026-11-19"),
        ).jsonObject
        assertEquals("CIMH", body["source"]!!.jsonPrimitive.content)
        assertEquals("L3", body["lineIds"]!!.jsonArray.single().jsonPrimitive.content)
        assertFalse("tracking" in body) // explicitNulls = false: the server reads a missing value as none
    }
}
