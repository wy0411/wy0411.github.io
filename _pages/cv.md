---
layout: archive
title: "CV"
permalink: /cv/
author_profile: true
redirect_from:
  - /resume
---

{% include base_path %}

Education
======
* Ph.D. in Computational Biology, Chinese Academy of Sciences, 2022 – present
* B.E. in Electronic Information Engineering, Jilin University, 2017 – 2021

Research Interests
======
* Bioinformatics
* Deep Learning
* Single-cell Transcriptomics
* Computational Immunology

Publications
======
  <ul>{% for post in site.publications reversed %}
    {% include archive-single-cv.html %}
  {% endfor %}</ul>
