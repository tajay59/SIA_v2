package bb.edu.cimh.sia.data

import kotlinx.serialization.Serializable
import kotlinx.serialization.serializer
import okhttp3.OkHttpClient

/** docs/api/orders.openapi.yaml, staff view: what M-06 to M-08 need. Unknown fields are ignored. */
@Serializable
data class RequestSummary(
    val id: String,
    val type: String,
    val status: String,
    val customerName: String? = null,
    val organisationName: String? = null,
    val lineCount: Int = 0,
    val waitingDays: Int? = null,
    val version: Int,
)

@Serializable
data class RequestPage(val items: List<RequestSummary>, val nextCursor: String? = null)

@Serializable
data class ProductSnapshot(val name: String, val type: String? = null, val modelname: String? = null)

@Serializable
data class Reservation(val status: String? = null, val units: List<String> = emptyList())

@Serializable
data class PickedUnit(val barcode: String, val pickedBy: String? = null, val pickedDate: String? = null)

@Serializable
data class RequestLine(
    val lineId: String,
    val productId: String,
    val product: ProductSnapshot,
    val qty: Int,
    /** CIMH or SUPPLIER, fixed by staff when the quote is sent ("view and sign", 2026-11-17). */
    val source: String? = null,
    val supplier: String? = null,
    val reservation: Reservation? = null,
    val picked: List<PickedUnit> = emptyList(),
)

@Serializable
data class ShippingAddress(
    val name: String? = null,
    val city: String? = null,
    val country: String? = null,
)

/** One parcel (CIMH stock, or a supplier shipping direct); only its lines matter here. */
@Serializable
data class Shipment(val id: String, val source: String? = null, val lineIds: List<String> = emptyList())

@Serializable
data class OrderRequest(
    val id: String,
    val type: String,
    val status: String,
    val customerName: String? = null,
    val organisationName: String? = null,
    val version: Int,
    val lines: List<RequestLine> = emptyList(),
    val shipTo: ShippingAddress? = null,
    val allowedActions: List<String> = emptyList(),
    val shipments: List<Shipment> = emptyList(),
) {
    /** Only CIMH-stock lines (paid) and every Pro Bono line are picked; supplier items ship direct. */
    val pickableLines: List<RequestLine> get() = lines.filter { type == "PROBONO" || it.source == "CIMH" }
    val allPicked: Boolean get() = pickableLines.all { it.picked.size >= it.qty }

    /** CIMH-stock / Pro Bono lines not yet in a shipment: what M-08 sends. Supplier parcels are recorded on the web. */
    val cimhToShip: List<RequestLine> get() {
        val shipped = shipments.flatMap { it.lineIds }.toSet()
        return pickableLines.filter { it.lineId !in shipped }
    }
}

@Serializable
data class PickForRequestBody(val lineId: String, val unit: String)

/** POST /requests/{id}/shipments: one CIMH parcel of picked lines (paid PURCHASING, Pro Bono PICKING). */
@Serializable
data class ShipmentInput(
    val lineIds: List<String>,
    val carrier: String,
    val tracking: String? = null,
    val note: String? = null,
    /** Required (2026-11-24): what CIMH paid to send the parcel, BBD with 2 decimals ("0.00" when nothing). */
    val cost: String,
    /** yyyy-MM-dd */
    val date: String,
    val notifyCustomer: Boolean = true,
    val source: String = "CIMH",
)

/** A typed shipping cost as the API's money string ("45" → "45.00", "45.5" → "45.50"); null when it isn't one. */
fun shippingCost(input: String): String? {
    val t = input.trim()
    if (!Regex("""^\d{1,12}(\.\d{1,2})?$""").matches(t)) return null
    val (whole, frac) = t.split('.').let { it[0] to it.getOrElse(1) { "" } }
    return "$whole.${frac.padEnd(2, '0')}"
}

class OrdersApi(baseUrl: String, client: OkHttpClient) {
    private val api = ApiClient(baseUrl, "orders", client)

    /** M-06: requests with units to pick or ship (same filter as the SIA web "To pick" tile). */
    suspend fun toPick(cursor: String? = null): RequestPage = api.get(
        api.url("requests", "scope" to "all", "status" to "APPROVED,PICKING,PURCHASING", "sort" to "waiting", "cursor" to cursor),
        serializer(),
    )

    suspend fun request(id: String): OrderRequest = api.get(api.url(listOf("requests", id)), serializer())

    /** Picks go through order-svc (it checks line, product and reservation, then asks inventory). */
    suspend fun pick(requestId: String, body: PickForRequestBody, key: String): OrderRequest =
        api.post(api.url(listOf("requests", requestId, "picks")), body, serializer(), serializer(), mapOf("Idempotency-Key" to key))

    /** Records one shipment; the request becomes SHIPPED when it covers the last unshipped line. */
    suspend fun ship(request: OrderRequest, body: ShipmentInput): OrderRequest =
        api.post(api.url(listOf("requests", request.id, "shipments")), body, serializer(), serializer(), mapOf("If-Match" to "\"${request.version}\""))
}
