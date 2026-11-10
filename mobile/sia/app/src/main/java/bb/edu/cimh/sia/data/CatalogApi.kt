package bb.edu.cimh.sia.data

import kotlinx.serialization.Serializable
import kotlinx.serialization.serializer
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/** docs/api/catalog.openapi.yaml, staff view: the fields M-03 shows. */
@Serializable
data class ProductSummary(
    val id: String,
    val name: String,
    val type: String? = null,
    val make: String? = null,
    val modelname: String? = null,
    val modelnumber: String? = null,
    val active: Boolean = true,
) {
    val subtitle: String get() = listOfNotNull(type, make, modelname, modelnumber).joinToString(" · ")
}

@Serializable
data class ProductPage(val items: List<ProductSummary>, val nextCursor: String? = null)

@Serializable
data class TypeOption(val key: String, val label: String)

@Serializable
data class Project(val code: String, val name: String, val active: Boolean = true)

@Serializable
data class Reference(
    val departments: List<String> = emptyList(),
    val types: List<TypeOption> = emptyList(),
    val projects: List<Project> = emptyList(),
)

/** ProductInput (strict on the server: only these fields, no coercion). */
@Serializable
data class ProductInput(
    val name: String,
    val type: String,
    val department: String,
    val sellable: Boolean,
    val probono: Boolean,
    val threshold: Int,
    val make: String? = null,
    val modelname: String? = null,
    val modelnumber: String? = null,
    val sn: String? = null,
    val sn1: String? = null,
    val description: String? = null,
    val details: String? = null,
    val project: String? = null,
    /** Money: "123.45" */
    val cost: String? = null,
    val unitquantity: Int? = null,
    val weight: Double? = null,
    val dimension: String? = null,
)

@Serializable
data class ImageJobs(val jobIds: List<String> = emptyList())

/** A photo to upload: JPEG/PNG/WebP bytes (≤ 20 MB, checked by the server). */
class Photo(val name: String, val mime: String, val bytes: ByteArray)

class CatalogApi(baseUrl: String, client: OkHttpClient) {
    private val api = ApiClient(baseUrl, "catalog", client)

    /** Name, make, model, keywords; staff also match serial prefixes. */
    suspend fun search(q: String, cursor: String? = null): ProductPage =
        api.get(api.url("products/search", "q" to q, "cursor" to cursor, "limit" to "25"), serializer())

    suspend fun product(id: String): ProductSummary = api.get(api.url(listOf("products", id)), serializer())

    suspend fun reference(): Reference = api.get(api.url("reference"), serializer())

    suspend fun create(input: ProductInput): ProductSummary =
        api.post(api.url("products"), input, serializer(), serializer())

    /** Processing is asynchronous (media-worker); the images appear on the product a little later. */
    suspend fun uploadImages(productId: String, photos: List<Photo>): ImageJobs {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
        photos.forEach { p -> body.addFormDataPart("files", p.name, p.bytes.toRequestBody(p.mime.toMediaType())) }
        val req = Request.Builder().url(api.url(listOf("products", productId, "images"))).post(body.build()).build()
        return api.execute(req) { r -> ApiJson.decodeFromString(ImageJobs.serializer(), r.body.string()) }
    }
}
