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
    val choice: String? = null,
    val reservation: Reservation? = null,
    val picked: List<PickedUnit> = emptyList(),
)

@Serializable
data class ShippingAddress(
    val name: String? = null,
    val city: String? = null,
    val country: String? = null,
)

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
) {
    /** Only CIMH-stock lines (paid) and every Pro Bono line are picked; supplier items ship direct. */
    val pickableLines: List<RequestLine> get() = lines.filter { type == "PROBONO" || it.choice == "CIMH" }
    val allPicked: Boolean get() = pickableLines.all { it.picked.size >= it.qty }
}

@Serializable
data class PickForRequestBody(val lineId: String, val unit: String)

@Serializable
data class ShipmentInput(
    val carrier: String,
    val tracking: String? = null,
    val note: String? = null,
    /** yyyy-MM-dd */
    val date: String,
    val notifyCustomer: Boolean = true,
)

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

    suspend fun ship(request: OrderRequest, body: ShipmentInput): OrderRequest =
        api.post(api.url(listOf("requests", request.id, "ship")), body, serializer(), serializer(), mapOf("If-Match" to "\"${request.version}\""))
}
