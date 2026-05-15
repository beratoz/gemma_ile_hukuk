package com.berat.legaltech.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

public record AnalyzeResponse(
        @JsonProperty("soru")
        String soru,
        @JsonProperty("cikarilan_kavramlar")
        List<String> cikarilanKavramlar,
        @JsonProperty("bulunan_madde_numaralari")
        List<String> bulunanMaddeNumaralari,
        @JsonProperty("mutalaa")
        String mutalaa
) {}
