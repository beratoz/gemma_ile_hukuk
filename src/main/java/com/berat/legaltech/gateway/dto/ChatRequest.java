package com.berat.legaltech.gateway.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ChatRequest(
        @NotBlank(message = "Soru bos olamaz")
        @Size(min = 3, max = 2000, message = "Soru 3-2000 karakter arasinda olmali")
        String soru
) {}
