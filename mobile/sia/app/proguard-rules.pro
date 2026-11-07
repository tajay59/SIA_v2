# kotlinx.serialization: keep generated serializers of our DTOs.
-keepclassmembers @kotlinx.serialization.Serializable class bb.edu.cimh.sia.** {
    *** Companion;
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class bb.edu.cimh.sia.**$$serializer { *; }
