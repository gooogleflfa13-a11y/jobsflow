\ProvidesClass{jobsflow-cover}[2026/07/31 Cross-industry cover letter]
\NeedsTeXFormat{LaTeX2e}
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{article}}
\ProcessOptions\relax
\LoadClass{article}

\usepackage[hmargin=2.3cm,vmargin=2.3cm]{geometry}
\usepackage[hidelinks]{hyperref}
\usepackage[usenames,dvipsnames]{xcolor}
\usepackage{titlesec}
\usepackage[absolute]{textpos}
\usepackage{fontspec}

% TeX Gyre Heros is a Helvetica-compatible font distributed with TeX Live.
% No third-party binary fonts are bundled in the JobsFlow repository.
\setmainfont{TeX Gyre Heros}
\setsansfont{TeX Gyre Heros}

\definecolor{date}{HTML}{666666}
\definecolor{primary}{HTML}{2B2B2B}
\definecolor{headings}{HTML}{6A6A6A}
\definecolor{subheadings}{HTML}{333333}

\setlength{\TPHorizModule}{1mm}
\setlength{\TPVertModule}{1mm}
\newcommand{\lastupdated}{\begin{textblock}{60}(155,5)
\color{date}\sffamily\fontsize{8pt}{10pt}\selectfont
Last Updated on \today
\end{textblock}}

\newcommand{\namesection}[3]{
\centering{\fontsize{40pt}{60pt}\sffamily\selectfont #1 #2}\\[5pt]
\centering{\color{headings}\sffamily\fontsize{11pt}{14pt}\selectfont #3}
\noindent\makebox[\linewidth]{\color{headings}\rule{\paperwidth}{0pt}}
}

\titlespacing{\section}{0pt}{0pt}{0pt}
\titlespacing{\subsection}{0pt}{0pt}{0pt}
\newcommand{\sectionsep}{\vspace{8pt}}

\titleformat{\section}
  {\color{headings}\scshape\sffamily\fontsize{16pt}{24pt}\selectfont\raggedright\uppercase}
  {}{0em}{}
\titleformat{\subsection}
  {\color{subheadings}\sffamily\fontsize{12pt}{12pt}\selectfont\bfseries\uppercase}
  {}{0em}{}

\newcommand{\runsubsection}[1]{\color{subheadings}\sffamily
  \fontsize{12pt}{12pt}\selectfont\bfseries\uppercase{#1}\normalfont}
\newcommand{\descript}[1]{\color{subheadings}\raggedright\scshape\sffamily
  \fontsize{11pt}{13pt}\selectfont{#1\\}\normalfont}
\newcommand{\location}[1]{\color{headings}\raggedright\sffamily
  \fontsize{10pt}{12pt}\selectfont{#1\\}\normalfont}

\newenvironment{tightemize}
  {\vspace{-\topsep}\begin{itemize}\itemsep1pt\parskip0pt\parsep0pt}
  {\end{itemize}\vspace{-\topsep}}

\newcommand{\companyname}[1]{\raggedright\sffamily\bfseries
  \fontsize{12pt}{14pt}\selectfont{#1\\}\normalfont}
\newcommand{\companyaddress}[1]{\raggedright\sffamily
  \fontsize{11pt}{13pt}\selectfont{#1\\}\mbox{}\\\mbox{}\\\normalfont}
\newcommand{\currentdate}[1]{\raggedleft\sffamily
  \fontsize{11pt}{13pt}\selectfont{#1\\}\normalfont}
\newcommand{\lettercontent}[1]{\raggedright\sffamily
  \fontsize{11pt}{13pt}\selectfont{#1\\}\mbox{}\\\normalfont}
\newcommand{\closing}[1]{\raggedright\sffamily
  \fontsize{11pt}{13pt}\selectfont{#1\\}\mbox{}\\\mbox{}\\\normalfont}
\newcommand{\signature}[1]{\raggedright\sffamily
  \fontsize{11pt}{13pt}\selectfont{#1\\}\normalfont}
